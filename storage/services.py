from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Count, Q
from .models import (
    GrainType, Granary, TemperatureHumidityLog,
    VentilationLog, PestInspection, RiskAssessment,
    Warning, DisposalTask, DisposalProgressLog, WarningNotifyLog,
    GrainSituationPrediction, InventoryChangeLog, AllocationConfig,
    AllocationSuggestion, AllocationExecution
)


class RiskCalculator:
    MOLD_WEIGHT = 0.6
    PEST_WEIGHT = 0.4
    LOW_RISK_THRESHOLD = 30
    HIGH_RISK_THRESHOLD = 70

    @classmethod
    def calculate_mold_risk(cls, granary, assess_date):
        grain_type = granary.grain_type
        temp_min = grain_type.safe_temp_min
        temp_max = grain_type.safe_temp_max
        hum_min = grain_type.safe_humidity_min
        hum_max = grain_type.safe_humidity_max

        recent_logs = TemperatureHumidityLog.objects.filter(
            granary=granary,
            record_date__lte=assess_date,
            record_date__gte=assess_date - timedelta(days=6)
        ).order_by('-record_date')

        if not recent_logs:
            return 0.0, 0

        temp_scores = []
        hum_scores = []
        exceed_days = 0

        for log in recent_logs:
            temp_dev = 0
            if log.temperature > temp_max:
                temp_dev = min((log.temperature - temp_max) * 5, 50)
                exceed_days += 1
            elif log.temperature < temp_min:
                temp_dev = min((temp_min - log.temperature) * 3, 30)
                exceed_days += 1
            temp_scores.append(temp_dev)

            hum_dev = 0
            if log.humidity > hum_max:
                hum_dev = min((log.humidity - hum_max) * 4, 50)
                if log.humidity > hum_max and exceed_days <= len(recent_logs) - len(temp_scores) + 1:
                    pass
            elif log.humidity < hum_min:
                hum_dev = min((hum_min - log.humidity) * 1.5, 20)
            hum_scores.append(hum_dev)

        for log in recent_logs:
            if (log.temperature > temp_max or log.temperature < temp_min or
                    log.humidity > hum_max or log.humidity < hum_min):
                pass

        exceed_count = 0
        for log in recent_logs:
            is_exceed = (log.temperature > temp_max or log.temperature < temp_min or
                         log.humidity > hum_max or log.humidity < hum_min)
            if is_exceed:
                exceed_count += 1

        avg_temp_score = sum(temp_scores) / len(temp_scores) if temp_scores else 0
        avg_hum_score = sum(hum_scores) / len(hum_scores) if hum_scores else 0

        base_score = avg_temp_score * 0.5 + avg_hum_score * 0.5

        exceed_bonus = (exceed_count / len(recent_logs)) * 20

        sensitivity_factor = grain_type.mold_sensitivity

        ventilation_factor = RiskAssessment.calculate_ventilation_factor(granary, assess_date)

        mold_score = (base_score + exceed_bonus) * sensitivity_factor * ventilation_factor
        mold_score = max(0.0, min(100.0, round(mold_score, 2)))

        return mold_score, exceed_count

    @classmethod
    def calculate_pest_risk(cls, granary, assess_date):
        grain_type = granary.grain_type

        recent_inspection = PestInspection.objects.filter(
            granary=granary,
            inspect_date__lte=assess_date,
            inspect_date__gte=assess_date - timedelta(days=14)
        ).order_by('-inspect_date').first()

        recent_log = TemperatureHumidityLog.objects.filter(
            granary=granary,
            record_date__lte=assess_date
        ).order_by('-record_date').first()

        if not recent_inspection:
            return 0.0

        density = recent_inspection.pest_density

        density_score = 0
        if density >= 10:
            density_score = 80
        elif density >= 5:
            density_score = 60
        elif density >= 2:
            density_score = 40
        elif density >= 1:
            density_score = 25
        elif density > 0:
            density_score = 10

        temp_factor = 1.0
        if recent_log:
            temp = recent_log.temperature
            if 25 <= temp <= 35:
                temp_factor = 1.5
            elif 20 <= temp < 25 or 35 < temp <= 38:
                temp_factor = 1.2
            elif temp < 15 or temp > 40:
                temp_factor = 0.6

        sensitivity_factor = grain_type.pest_sensitivity

        ventilation_factor = RiskAssessment.calculate_ventilation_factor(granary, assess_date)

        pest_score = density_score * temp_factor * sensitivity_factor * ventilation_factor
        pest_score = max(0.0, min(100.0, round(pest_score, 2)))

        return pest_score

    @classmethod
    def calculate_overall_risk(cls, mold_score, pest_score):
        overall = mold_score * cls.MOLD_WEIGHT + pest_score * cls.PEST_WEIGHT
        return round(overall, 2)

    @classmethod
    def determine_risk_level(cls, overall_score):
        if overall_score < cls.LOW_RISK_THRESHOLD:
            return 'low'
        elif overall_score < cls.HIGH_RISK_THRESHOLD:
            return 'medium'
        else:
            return 'high'

    @classmethod
    def assess_granary(cls, granary, assess_date):
        consecutive_days = granary.get_consecutive_days()
        has_continuous = granary.has_continuous_data(days=3)

        mold_score, _ = cls.calculate_mold_risk(granary, assess_date)
        pest_score = cls.calculate_pest_risk(granary, assess_date)
        ventilation_factor = RiskAssessment.calculate_ventilation_factor(granary, assess_date)
        overall_score = cls.calculate_overall_risk(mold_score, pest_score)
        risk_level = cls.determine_risk_level(overall_score)

        assessment = RiskAssessment(
            granary=granary,
            assess_date=assess_date,
            mold_risk_score=mold_score,
            pest_risk_score=pest_score,
            ventilation_factor=ventilation_factor,
            overall_risk_score=overall_score,
            risk_level=risk_level,
            is_formal=has_continuous,
            consecutive_days=consecutive_days,
        )
        return assessment

    @classmethod
    def assess_all_granaries(cls, assess_date):
        granaries = Granary.objects.filter(is_active=True)
        assessments = []
        for granary in granaries:
            assessment = cls.assess_granary(granary, assess_date)
            assessments.append(assessment)
        RiskAssessment.objects.bulk_create(assessments)
        return assessments


def recalculate_risks_after_ventilation(ventilation_log):
    granary = ventilation_log.granary
    recalculate_risks_for_granary(granary)


def recalculate_risks_for_granary(granary, days=30):
    from django.utils import timezone as tz
    today = date.today()
    start_date = today - timedelta(days=days - 1)

    all_dates = [start_date + timedelta(days=i) for i in range(days)]

    existing_map = {}
    for ra in RiskAssessment.objects.filter(granary=granary, assess_date__gte=start_date, assess_date__lte=today):
        existing_map[ra.assess_date] = ra

    updated = 0
    created = 0
    for d in all_dates:
        has_th = TemperatureHumidityLog.objects.filter(granary=granary, record_date__lte=d).exists()
        has_pest = PestInspection.objects.filter(granary=granary, inspect_date__lte=d).exists()
        if not has_th and not has_pest:
            continue

        assess = RiskCalculator.assess_granary(granary, d)

        if d in existing_map:
            existing = existing_map[d]
            existing.mold_risk_score = assess.mold_risk_score
            existing.pest_risk_score = assess.pest_risk_score
            existing.ventilation_factor = assess.ventilation_factor
            existing.overall_risk_score = assess.overall_risk_score
            existing.risk_level = assess.risk_level
            existing.is_formal = assess.is_formal
            existing.consecutive_days = assess.consecutive_days
            existing.save()
            updated += 1
        else:
            assess.save()
            created += 1

    return updated, created


class WarningService:
    @staticmethod
    def generate_warning_from_assessment(assessment, notify_person=None):
        if not assessment or assessment.risk_level == 'low':
            return None

        existing = Warning.objects.filter(
            granary=assessment.granary,
            risk_assessment=assessment
        ).first()
        if existing:
            return existing

        warning_level = Warning.get_level_from_risk(assessment.risk_level)

        content_parts = []
        if assessment.mold_risk_score >= 50:
            content_parts.append(f'霉变风险评分{assessment.mold_risk_score}')
        if assessment.pest_risk_score >= 50:
            content_parts.append(f'虫害风险评分{assessment.pest_risk_score}')
        if assessment.overall_risk_score >= 70:
            content_parts.append(f'综合风险评分{assessment.overall_risk_score}')

        content = f'粮仓{assessment.granary.code}存在'
        if assessment.risk_level == 'high':
            content += '高'
        elif assessment.risk_level == 'medium':
            content += '中'
        content += '风险'
        if content_parts:
            content += '：' + '、'.join(content_parts)

        warning = Warning.objects.create(
            granary=assessment.granary,
            risk_assessment=assessment,
            warning_level=warning_level,
            trigger_type='auto',
            notify_method='system',
            warning_content=content,
            notified_person=notify_person or '系统管理员',
        )

        WarningService.create_notify_log(warning)
        return warning

    @staticmethod
    def generate_warnings_for_date(assess_date):
        assessments = RiskAssessment.objects.filter(
            assess_date=assess_date,
            risk_level__in=['medium', 'high']
        ).select_related('granary')

        created = []
        for assessment in assessments:
            warning = WarningService.generate_warning_from_assessment(assessment)
            if warning:
                created.append(warning)
        return created

    @staticmethod
    def create_manual_warning(granary, warning_level, content, trigger_person, notify_method='system'):
        warning = Warning.objects.create(
            granary=granary,
            warning_level=warning_level,
            trigger_type='manual',
            notify_method=notify_method,
            warning_content=content,
            notified_person=trigger_person,
        )
        WarningService.create_notify_log(warning)
        return warning

    @staticmethod
    def create_notify_log(warning):
        notify_content = WarningService.build_notify_content(warning)
        return WarningNotifyLog.objects.create(
            warning=warning,
            notify_method=warning.notify_method,
            notify_target=warning.notified_person or '系统管理员',
            notify_content=notify_content,
        )

    @staticmethod
    def build_notify_content(warning):
        return (f'【{warning.get_warning_level_display()}】'
                f'粮仓{warning.granary.code}于{warning.warning_time.strftime("%Y-%m-%d %H:%M")}触发预警。'
                f'预警内容：{warning.warning_content}。'
                f'请在{warning.get_deadline_hours()}小时内处置。')

    @staticmethod
    def check_and_update_overdue():
        now = timezone.now()
        warnings = Warning.objects.filter(
            status__in=['pending', 'processing']
        ).select_related('granary')
        overdue_count = 0
        for warning in warnings:
            if warning.check_overdue() and not warning.is_overdue:
                warning.is_overdue = True
                warning.save()
                overdue_count += 1
                WarningNotifyLog.objects.create(
                    warning=warning,
                    notify_method='system',
                    notify_target=warning.notified_person or '系统管理员',
                    notify_content=f'【超时提醒】粮仓{warning.granary.code}的预警已超过处置时限，请尽快处理！',
                )

        tasks = DisposalTask.objects.filter(
            status__in=['assigned', 'in_progress']
        ).select_related('warning__granary')
        overdue_task_count = 0
        for task in tasks:
            if task.is_overdue():
                overdue_task_count += 1
                WarningNotifyLog.objects.create(
                    warning=task.warning,
                    notify_method='system',
                    notify_target=task.assignee,
                    notify_content=f'【任务超时提醒】处置任务"{task.task_title}"已超过要求完成时间，请尽快处理！',
                )

        return overdue_count, overdue_task_count


class DisposalService:
    @staticmethod
    def assign_task(warning, task_title, assignee, assigner, deadline=None,
                    task_description=None, priority=None):
        if priority is None:
            if warning.warning_level == 'level1':
                priority = 'urgent'
            elif warning.warning_level == 'level2':
                priority = 'high'
            else:
                priority = 'normal'

        if deadline is None:
            hours = warning.get_deadline_hours()
            deadline = warning.warning_time + timedelta(hours=hours)

        task = DisposalTask.objects.create(
            warning=warning,
            task_title=task_title,
            task_description=task_description,
            assignee=assignee,
            assigner=assigner,
            deadline=deadline,
            priority=priority,
        )

        if warning.status == 'pending':
            warning.status = 'processing'
            warning.save()

        DisposalProgressLog.objects.create(
            task=task,
            progress_percent=0,
            progress_description=f'任务已分派给{assignee}',
            operator=assigner or '系统',
        )
        return task

    @staticmethod
    def update_progress(task, progress_percent, description, operator, remark=None):
        if progress_percent < task.progress:
            progress_percent = task.progress

        task.progress = progress_percent
        if progress_percent > 0 and task.status == 'assigned':
            task.status = 'in_progress'
        task.save()

        return DisposalProgressLog.objects.create(
            task=task,
            progress_percent=progress_percent,
            progress_description=description,
            operator=operator,
            remark=remark,
        )

    @staticmethod
    def submit_for_review(task, disposal_measures, disposal_result, operator, attachment=None):
        task.disposal_measures = disposal_measures
        task.disposal_result = disposal_result
        task.disposal_attachment = attachment
        task.progress = 100
        task.status = 'submitted'
        task.completed_time = timezone.now()
        task.save()

        if task.warning.status == 'processing':
            task.warning.status = 'reviewing'
            task.warning.save()

        DisposalProgressLog.objects.create(
            task=task,
            progress_percent=100,
            progress_description=f'处置完成，提交复查。处置结果：{disposal_result}',
            operator=operator,
        )
        return task

    @staticmethod
    def review_task(task, reviewer, passed, opinion=None):
        task.reviewer = reviewer
        task.review_time = timezone.now()
        task.review_passed = passed
        task.review_opinion = opinion

        if passed:
            task.status = 'closed'
            if task.warning.status == 'reviewing':
                task.warning.status = 'closed'
                task.warning.save()
        else:
            task.status = 'review_failed'
            task.progress = 50

        task.save()

        DisposalProgressLog.objects.create(
            task=task,
            progress_percent=100 if passed else 50,
            progress_description=f'复查{"通过" if passed else "不通过"}。复查意见：{opinion or "无"}',
            operator=reviewer,
        )
        return task

    @staticmethod
    def archive_task(task, archived_by, remark=None):
        if task.status != 'closed':
            raise ValueError('只有已闭环的任务才能归档')
        if not task.review_passed:
            raise ValueError('未通过复查的任务不能归档')

        task.archived_by = archived_by
        task.archived_time = timezone.now()
        task.archive_remark = remark
        task.save()
        return task

    @staticmethod
    def redo_task(task, operator):
        task.status = 'in_progress'
        task.progress = 50
        task.review_passed = False
        task.reviewer = None
        task.review_time = None
        task.review_opinion = None
        task.save()

        if task.warning.status == 'reviewing':
            task.warning.status = 'processing'
            task.warning.save()

        DisposalProgressLog.objects.create(
            task=task,
            progress_percent=50,
            progress_description='复查不通过，重新进行处置',
            operator=operator,
        )
        return task


class WarningStatisticsService:
    @staticmethod
    def get_overview_stats(start_date=None, end_date=None):
        qs = Warning.objects.all()
        task_qs = DisposalTask.objects.all()

        if start_date:
            qs = qs.filter(warning_time__date__gte=start_date)
            task_qs = task_qs.filter(assigned_time__date__gte=start_date)
        if end_date:
            qs = qs.filter(warning_time__date__lte=end_date)
            task_qs = task_qs.filter(assigned_time__date__lte=end_date)

        total = qs.count()
        level1 = qs.filter(warning_level='level1').count()
        level2 = qs.filter(warning_level='level2').count()
        level3 = qs.filter(warning_level='level3').count()
        pending = qs.filter(status='pending').count()
        processing = qs.filter(status='processing').count()
        reviewing = qs.filter(status='reviewing').count()
        closed = qs.filter(status='closed').count()
        overdue = qs.filter(is_overdue=True).count()

        task_total = task_qs.count()
        task_closed = task_qs.filter(status='closed').count()
        task_in_progress = task_qs.filter(status__in=['assigned', 'in_progress']).count()
        task_reviewing = task_qs.filter(status='submitted').count()

        return {
            'total_warnings': total,
            'level1_count': level1,
            'level2_count': level2,
            'level3_count': level3,
            'pending_count': pending,
            'processing_count': processing,
            'reviewing_count': reviewing,
            'in_progress_count': processing + reviewing,
            'closed_count': closed,
            'overdue_count': overdue,
            'closure_rate': round(closed / total * 100, 1) if total > 0 else 0,
            'total_tasks': task_total,
            'tasks_closed': task_closed,
            'tasks_in_progress': task_in_progress,
            'tasks_reviewing': task_reviewing,
            'task_closure_rate': round(task_closed / task_total * 100, 1) if task_total > 0 else 0,
        }

    @staticmethod
    def get_by_granary(start_date=None, end_date=None):
        qs = Warning.objects.all()
        if start_date:
            qs = qs.filter(warning_time__date__gte=start_date)
        if end_date:
            qs = qs.filter(warning_time__date__lte=end_date)

        data = qs.values(
            'granary__id', 'granary__code', 'granary__name', 'warning_level'
        ).annotate(
            count=Count('id')
        ).order_by('granary__code')

        result = {}
        for item in data:
            gid = item['granary__id']
            if gid not in result:
                result[gid] = {
                    'id': gid,
                    'code': item['granary__code'],
                    'name': item['granary__name'],
                    'level1': 0,
                    'level2': 0,
                    'level3': 0,
                    'total': 0,
                }
            result[gid][item['warning_level']] = item['count']
            result[gid]['total'] += item['count']

        return sorted(result.values(), key=lambda x: -x['total'])

    @staticmethod
    def get_by_date_trend(days=30, start_date=None, end_date=None):
        if start_date and end_date:
            pass
        elif end_date:
            start_date = end_date - timedelta(days=days - 1)
        elif start_date:
            end_date = start_date + timedelta(days=days - 1)
        else:
            end_date = date.today()
            start_date = end_date - timedelta(days=days - 1)

        delta_days = (end_date - start_date).days + 1

        qs = Warning.objects.filter(
            warning_time__date__gte=start_date,
            warning_time__date__lte=end_date
        )

        data = qs.extra(
            select={'date': 'DATE(warning_time)'}
        ).values('date', 'warning_level').annotate(
            count=Count('id')
        ).order_by('date')

        date_list = [start_date + timedelta(days=i) for i in range(delta_days)]
        result = []
        data_map = {}
        for item in data:
            d = str(item['date'])
            if d not in data_map:
                data_map[d] = {'level1': 0, 'level2': 0, 'level3': 0, 'total': 0}
            data_map[d][item['warning_level']] = item['count']
            data_map[d]['total'] += item['count']

        for d in date_list:
            ds = d.strftime('%Y-%m-%d')
            entry = data_map.get(ds, {'level1': 0, 'level2': 0, 'level3': 0, 'total': 0})
            result.append({
                'date': ds,
                'label': d.strftime('%m-%d'),
                **entry
            })
        return result

    @staticmethod
    def get_disposal_efficiency(start_date=None, end_date=None):
        task_qs = DisposalTask.objects.filter(status='closed')
        if start_date:
            task_qs = task_qs.filter(completed_time__date__gte=start_date)
        if end_date:
            task_qs = task_qs.filter(completed_time__date__lte=end_date)

        total = 0
        on_time = 0
        total_hours = 0
        for task in task_qs:
            total += 1
            if not task.is_overdue():
                on_time += 1
            if task.completed_time and task.assigned_time:
                delta = task.completed_time - task.assigned_time
                total_hours += delta.total_seconds() / 3600

        return {
            'total_closed': total,
            'on_time_count': on_time,
            'overdue_count': total - on_time,
            'on_time_rate': round(on_time / total * 100, 1) if total > 0 else 0,
            'avg_hours': round(total_hours / total, 1) if total > 0 else 0,
        }


class GrainSituationPredictionService:
    @staticmethod
    def _calculate_linear_trend(values, days):
        if not values:
            return 0, 'stable'
        n = len(values)
        if n < 2:
            return values[-1] if values else 0, 'stable'
        x = list(range(n))
        y = values
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        denominator = sum((xi - mean_x) ** 2 for xi in x)
        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator
        intercept = mean_y - slope * mean_x
        predicted = slope * (n - 1 + days) + intercept
        if slope > 0.1:
            trend = 'deteriorating'
        elif slope < -0.1:
            trend = 'improving'
        else:
            trend = 'stable'
        return predicted, trend

    @staticmethod
    def _calculate_confidence(data_points, min_points=7):
        if data_points >= min_points:
            return min(95.0, 70.0 + (data_points - min_points) * 3.5)
        return max(50.0, 50.0 + data_points * 3.0)

    @classmethod
    def predict_granary(cls, granary, prediction_date, horizon_days=7):
        target_date = prediction_date + timedelta(days=horizon_days)

        existing = GrainSituationPrediction.objects.filter(
            granary=granary,
            prediction_date=prediction_date,
            horizon_days=horizon_days,
            target_date=target_date
        ).first()
        if existing:
            return existing

        temp_logs = TemperatureHumidityLog.objects.filter(
            granary=granary,
            record_date__lte=prediction_date,
            record_date__gte=prediction_date - timedelta(days=30)
        ).order_by('record_date')
        pest_logs = PestInspection.objects.filter(
            granary=granary,
            inspect_date__lte=prediction_date,
            inspect_date__gte=prediction_date - timedelta(days=30)
        ).order_by('inspect_date')
        risk_logs = RiskAssessment.objects.filter(
            granary=granary,
            assess_date__lte=prediction_date,
            assess_date__gte=prediction_date - timedelta(days=30)
        ).order_by('assess_date')
        inventory_logs = InventoryChangeLog.objects.filter(
            granary=granary,
            change_date__lte=prediction_date,
            change_date__gte=prediction_date - timedelta(days=30)
        ).order_by('change_date')

        temps = [log.temperature for log in temp_logs]
        hums = [log.humidity for log in temp_logs]
        pests = [log.pest_density for log in pest_logs]
        mold_risks = [log.mold_risk_score for log in risk_logs]
        pest_risks = [log.pest_risk_score for log in risk_logs]
        overall_risks = [log.overall_risk_score for log in risk_logs]

        pred_temp, temp_trend = cls._calculate_linear_trend(temps, horizon_days)
        pred_hum, hum_trend = cls._calculate_linear_trend(hums, horizon_days)
        pred_pest, pest_trend = cls._calculate_linear_trend(pests, horizon_days)
        pred_mold_risk, mold_trend = cls._calculate_linear_trend(mold_risks, horizon_days)
        pred_pest_risk, pest_risk_trend = cls._calculate_linear_trend(pest_risks, horizon_days)
        pred_overall_risk, risk_trend = cls._calculate_linear_trend(overall_risks, horizon_days)

        grain_type = granary.grain_type
        pred_temp = max(grain_type.safe_temp_min - 5, min(grain_type.safe_temp_max + 10, pred_temp))
        pred_hum = max(grain_type.safe_humidity_min - 10, min(grain_type.safe_humidity_max + 10, pred_hum))
        pred_pest = max(0, min(20, pred_pest))
        pred_mold_risk = max(0, min(100, pred_mold_risk))
        pred_pest_risk = max(0, min(100, pred_pest_risk))
        pred_overall_risk = max(0, min(100, pred_overall_risk))

        if pred_overall_risk < 30:
            risk_level = 'low'
        elif pred_overall_risk < 70:
            risk_level = 'medium'
        else:
            risk_level = 'high'

        current_inventory = granary.current_stock
        pred_inventory = current_inventory
        inventory_trend = 'stable'
        if inventory_logs:
            daily_changes = {}
            for log in inventory_logs:
                d = log.change_date
                if d not in daily_changes:
                    daily_changes[d] = 0
                if log.change_type in ('in', 'transfer_in'):
                    daily_changes[d] += log.quantity
                elif log.change_type in ('out', 'transfer_out'):
                    daily_changes[d] -= log.quantity
            change_values = list(daily_changes.values())
            avg_change = sum(change_values) / len(change_values) if change_values else 0
            pred_inventory = current_inventory + avg_change * horizon_days
            pred_inventory = max(0, min(granary.capacity, pred_inventory))
            if avg_change > 0.5:
                inventory_trend = 'improving' if current_inventory < granary.capacity * 0.5 else 'deteriorating'
            elif avg_change < -0.5:
                inventory_trend = 'deteriorating' if current_inventory > granary.capacity * 0.3 else 'improving'

        confidence = cls._calculate_confidence(len(temp_logs))

        config = AllocationConfig.objects.filter(is_default=True).first()
        high_risk_threshold = config.high_risk_threshold if config else 70.0
        high_inv_threshold = config.high_inventory_threshold if config else 85.0
        low_inv_threshold = config.low_inventory_threshold if config else 20.0

        is_high_risk = pred_overall_risk >= high_risk_threshold
        inv_ratio = (pred_inventory / granary.capacity * 100) if granary.capacity > 0 else 0
        is_inventory_pressure = inv_ratio >= high_inv_threshold or inv_ratio <= low_inv_threshold

        warning_message = ''
        warnings = []
        if is_high_risk:
            warnings.append(f'预测{horizon_days}天后综合风险评分将达到{pred_overall_risk:.1f}，处于高风险状态')
        if inv_ratio >= high_inv_threshold:
            warnings.append(f'预测库存将达到{pred_inventory:.1f}吨，占容量的{inv_ratio:.1f}%，库存过高')
        elif inv_ratio <= low_inv_threshold:
            warnings.append(f'预测库存将降至{pred_inventory:.1f}吨，占容量的{inv_ratio:.1f}%，库存不足')
        if warnings:
            warning_message = '；'.join(warnings)

        prediction = GrainSituationPrediction.objects.create(
            granary=granary,
            prediction_date=prediction_date,
            horizon_days=horizon_days,
            target_date=target_date,
            predicted_temp=round(pred_temp, 1),
            predicted_humidity=round(pred_hum, 1),
            predicted_pest_density=round(pred_pest, 2),
            predicted_mold_risk=round(pred_mold_risk, 2),
            predicted_pest_risk=round(pred_pest_risk, 2),
            predicted_overall_risk=round(pred_overall_risk, 2),
            predicted_risk_level=risk_level,
            predicted_inventory=round(pred_inventory, 2),
            temp_trend=temp_trend,
            humidity_trend=hum_trend,
            risk_trend=risk_trend,
            inventory_trend=inventory_trend,
            confidence_score=round(confidence, 1),
            is_high_risk=is_high_risk,
            is_inventory_pressure=is_inventory_pressure,
            warning_message=warning_message,
        )
        return prediction

    @classmethod
    def predict_all_granaries(cls, prediction_date, horizon_days=7, granary=None):
        if granary:
            granaries = [granary]
        else:
            granaries = Granary.objects.filter(is_active=True)
        predictions = []
        for g in granaries:
            try:
                pred = cls.predict_granary(g, prediction_date, horizon_days)
                predictions.append(pred)
            except Exception:
                continue
        return predictions

    @staticmethod
    def get_high_risk_predictions(horizon_days=7):
        today = date.today()
        return GrainSituationPrediction.objects.filter(
            prediction_date=today,
            horizon_days=horizon_days,
            is_high_risk=True
        ).select_related('granary').order_by('-predicted_overall_risk')

    @staticmethod
    def get_inventory_pressure_predictions(horizon_days=7):
        today = date.today()
        return GrainSituationPrediction.objects.filter(
            prediction_date=today,
            horizon_days=horizon_days,
            is_inventory_pressure=True
        ).select_related('granary').order_by('-predicted_inventory')


class InventoryService:
    @staticmethod
    def create_change_log(granary, change_type, quantity, grain_type=None,
                          operator=None, remark=None, related_allocation=None):
        if grain_type is None:
            grain_type = granary.grain_type
        if change_type in ('in', 'transfer_in', 'adjust') and quantity > 0:
            balance_after = granary.current_stock + quantity
        elif change_type in ('out', 'transfer_out') and quantity < 0:
            balance_after = granary.current_stock + quantity
        else:
            balance_after = granary.current_stock + quantity

        if balance_after < 0:
            raise ValueError('库存不足，无法完成出库操作')
        if balance_after > granary.capacity:
            raise ValueError('库存将超过设计容量')

        log = InventoryChangeLog.objects.create(
            granary=granary,
            change_date=date.today(),
            change_type=change_type,
            quantity=quantity,
            balance_after=balance_after,
            grain_type=grain_type,
            operator=operator,
            remark=remark,
            related_allocation=related_allocation,
        )

        granary.current_stock = balance_after
        granary.save()

        return log

    @staticmethod
    def get_inventory_turnover(granary, days=30):
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        logs = InventoryChangeLog.objects.filter(
            granary=granary,
            change_date__gte=start_date,
            change_date__lte=end_date,
            change_type__in=['out', 'transfer_out']
        )
        total_out = sum(log.quantity for log in logs if log.quantity < 0)
        total_out = abs(total_out)
        avg_stock = granary.current_stock
        if avg_stock > 0:
            turnover_rate = total_out / avg_stock
            turnover_days = days / turnover_rate if turnover_rate > 0 else 999
        else:
            turnover_rate = 0
            turnover_days = 999
        return {
            'total_out': round(total_out, 2),
            'avg_stock': round(avg_stock, 2),
            'turnover_rate': round(turnover_rate, 3),
            'turnover_days': round(turnover_days, 1),
        }


class AllocationService:
    @staticmethod
    def _calculate_priority_score(source, target, config):
        risk_diff = max(0, source['risk_score'] - target['risk_score'])
        inv_diff = max(0, source['inv_ratio'] - target['inv_ratio'])
        distance_score = 50.0

        risk_component = risk_diff * config.risk_weight
        inv_component = inv_diff * config.inventory_weight
        distance_component = distance_score * config.distance_weight

        score = risk_component + inv_component + distance_component
        return min(100.0, max(0.0, score))

    @staticmethod
    def _determine_priority_level(score):
        if score >= 75:
            return 'urgent'
        elif score >= 50:
            return 'high'
        else:
            return 'normal'

    @staticmethod
    def _generate_execution_no():
        today = date.today()
        count = AllocationExecution.objects.filter(
            created_at__date=today
        ).count() + 1
        return f'DB{today.strftime("%Y%m%d")}{count:04d}'

    @classmethod
    def generate_allocation_suggestions(cls, config=None, grain_type_filter=None):
        if config is None:
            config = AllocationConfig.objects.filter(is_default=True).first()
            if config is None:
                raise ValueError('未找到默认调拨配置，请先创建配置')

        today = date.today()
        predictions = GrainSituationPrediction.objects.filter(
            prediction_date=today,
            horizon_days__in=[7, 14, 30]
        ).select_related('granary')

        granary_data = {}
        for pred in predictions:
            gid = pred.granary_id
            if gid not in granary_data:
                g = pred.granary
                capacity = g.capacity if g.capacity > 0 else 1
                inv_ratio = (g.current_stock / capacity) * 100
                latest_risk = RiskAssessment.objects.filter(
                    granary=g
                ).order_by('-assess_date').first()
                granary_data[gid] = {
                    'granary': g,
                    'current_stock': g.current_stock,
                    'capacity': capacity,
                    'inv_ratio': inv_ratio,
                    'risk_score': latest_risk.overall_risk_score if latest_risk else 0,
                    'predicted_risk': pred.predicted_overall_risk,
                    'predicted_inventory': pred.predicted_inventory or g.current_stock,
                    'is_high_risk': pred.is_high_risk,
                    'is_inventory_pressure': pred.is_inventory_pressure,
                    'prediction': pred,
                }

        sources = []
        targets = []
        for gid, data in granary_data.items():
            if grain_type_filter and data['granary'].grain_type_id != grain_type_filter.id:
                continue
            is_source = (
                data['inv_ratio'] >= config.high_inventory_threshold or
                data['is_inventory_pressure'] and data['predicted_inventory'] > data['current_stock']
            )
            is_target = (
                data['inv_ratio'] <= config.low_inventory_threshold or
                data['is_high_risk'] or
                data['is_inventory_pressure'] and data['predicted_inventory'] < data['current_stock']
            )
            if is_source and data['current_stock'] > config.min_transfer_quantity:
                sources.append(data)
            if is_target:
                targets.append(data)

        suggestions = []
        for source in sources:
            for target in targets:
                if source['granary'].id == target['granary'].id:
                    continue
                if not config.allow_cross_grain_type and source['granary'].grain_type_id != target['granary'].grain_type_id:
                    continue

                available = source['current_stock'] - (source['capacity'] * config.safety_stock_ratio / 100)
                needed = (target['capacity'] * config.safety_stock_ratio / 100) - target['current_stock']

                if available <= 0 or needed <= 0:
                    continue

                quantity = min(available, needed, config.max_transfer_quantity)
                if quantity < config.min_transfer_quantity:
                    continue

                priority_score = cls._calculate_priority_score(source, target, config)
                priority_level = cls._determine_priority_level(priority_score)

                reason_parts = []
                if target['is_high_risk']:
                    reason_parts.append(f'目标仓{target["granary"].code}预测风险较高（{target["predicted_risk"]:.1f}分）')
                if target['inv_ratio'] <= config.low_inventory_threshold:
                    reason_parts.append(f'目标仓库存不足（当前{target["inv_ratio"]:.1f}%）')
                if source['inv_ratio'] >= config.high_inventory_threshold:
                    reason_parts.append(f'源仓库存过高（当前{source["inv_ratio"]:.1f}%）')
                reason = '；'.join(reason_parts) if reason_parts else '基于粮情预测和库存优化的调拨建议'

                expected_benefit = (
                    f'预计可使源仓库存占比从{source["inv_ratio"]:.1f}%降至'
                    f'{((source["current_stock"] - quantity) / source["capacity"] * 100):.1f}%，'
                    f'目标仓库存占比从{target["inv_ratio"]:.1f}%升至'
                    f'{((target["current_stock"] + quantity) / target["capacity"] * 100):.1f}%'
                )

                existing = AllocationSuggestion.objects.filter(
                    source_granary=source['granary'],
                    target_granary=target['granary'],
                    grain_type=source['granary'].grain_type,
                    status__in=['pending', 'approved']
                ).first()
                if existing:
                    continue

                suggestion = AllocationSuggestion.objects.create(
                    source_granary=source['granary'],
                    target_granary=target['granary'],
                    grain_type=source['granary'].grain_type,
                    suggested_quantity=round(quantity, 2),
                    priority_score=round(priority_score, 2),
                    priority_level=priority_level,
                    reason=reason,
                    expected_benefit=expected_benefit,
                    source_risk_score=source['risk_score'],
                    target_risk_score=target['risk_score'],
                    source_inventory_ratio=round(source['inv_ratio'], 2),
                    target_inventory_ratio=round(target['inv_ratio'], 2),
                    config=config,
                    prediction=source['prediction'],
                )

                if quantity <= config.auto_approve_below:
                    suggestion.status = 'approved'
                    suggestion.approved_by = '系统自动审批'
                    suggestion.approved_at = timezone.now()
                    suggestion.approval_opinion = '调拨数量低于自动审批阈值，系统自动批准'
                    suggestion.save()
                    cls.create_execution(suggestion, operator='系统')

                suggestions.append(suggestion)

        return suggestions

    @staticmethod
    def approve_suggestion(suggestion, approved_by, approval_opinion=None):
        if suggestion.status != 'pending':
            raise ValueError('只有待审核状态的建议才能审批')
        suggestion.status = 'approved'
        suggestion.approved_by = approved_by
        suggestion.approved_at = timezone.now()
        suggestion.approval_opinion = approval_opinion
        suggestion.save()
        return AllocationService.create_execution(suggestion, operator=approved_by)

    @staticmethod
    def reject_suggestion(suggestion, approved_by, approval_opinion=None):
        if suggestion.status != 'pending':
            raise ValueError('只有待审核状态的建议才能审批')
        suggestion.status = 'rejected'
        suggestion.approved_by = approved_by
        suggestion.approved_at = timezone.now()
        suggestion.approval_opinion = approval_opinion
        suggestion.save()
        return suggestion

    @classmethod
    def create_execution(cls, suggestion, operator=None):
        if hasattr(suggestion, 'execution') and suggestion.execution:
            return suggestion.execution
        if suggestion.status != 'approved':
            raise ValueError('只有已批准的建议才能创建执行单')
        execution = AllocationExecution.objects.create(
            suggestion=suggestion,
            execution_no=cls._generate_execution_no(),
            operator=operator,
        )
        return execution

    @staticmethod
    def update_execution_status(execution, status, operator=None, **kwargs):
        execution.status = status
        if status == 'completed':
            execution.completed_at = timezone.now()
            if execution.actual_quantity is None:
                execution.actual_quantity = execution.suggestion.suggested_quantity
        for key, value in kwargs.items():
            if hasattr(execution, key):
                setattr(execution, key, value)
        if operator:
            execution.operator = operator
        execution.save()

        if status == 'completed' and execution.status == 'completed':
            suggestion = execution.suggestion
            suggestion.status = 'executed'
            suggestion.save()

            source = suggestion.source_granary
            target = suggestion.target_granary
            qty = execution.actual_quantity or suggestion.suggested_quantity
            loss = execution.loss_quantity or 0
            net_qty = qty - loss

            InventoryService.create_change_log(
                granary=source,
                change_type='transfer_out',
                quantity=-qty,
                grain_type=suggestion.grain_type,
                operator=operator,
                remark=f'调拨出库至{target.code}，调拨单号{execution.execution_no}',
                related_allocation=execution,
            )
            InventoryService.create_change_log(
                granary=target,
                change_type='transfer_in',
                quantity=net_qty,
                grain_type=suggestion.grain_type,
                operator=operator,
                remark=f'调拨入库自{source.code}，调拨单号{execution.execution_no}，损耗{loss}吨',
                related_allocation=execution,
            )
        return execution

    @staticmethod
    def get_allocation_efficiency(days=30):
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        executions = AllocationExecution.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        total = executions.count()
        completed = executions.filter(status='completed').count()
        total_qty = 0
        total_loss = 0
        total_transit_hours = 0
        transit_count = 0
        for exec in executions.filter(status='completed'):
            actual_qty = exec.actual_quantity or exec.suggestion.suggested_quantity
            total_qty += actual_qty
            total_loss += exec.loss_quantity or 0
            transit = exec.get_transit_hours()
            if transit:
                total_transit_hours += transit
                transit_count += 1
        return {
            'total_allocations': total,
            'completed_count': completed,
            'pending_count': total - completed,
            'completion_rate': round(completed / total * 100, 1) if total > 0 else 0,
            'total_quantity': round(total_qty, 2),
            'total_loss': round(total_loss, 2),
            'loss_rate': round(total_loss / total_qty * 100, 2) if total_qty > 0 else 0,
            'avg_transit_hours': round(total_transit_hours / transit_count, 2) if transit_count > 0 else 0,
        }


class PredictionStatisticsService:
    @staticmethod
    def get_overview_stats(horizon_days=7):
        today = date.today()
        predictions = GrainSituationPrediction.objects.filter(
            prediction_date=today,
            horizon_days=horizon_days
        ).select_related('granary')

        total = predictions.count()
        high_risk = predictions.filter(is_high_risk=True).count()
        inventory_pressure = predictions.filter(is_inventory_pressure=True).count()
        avg_confidence = predictions.aggregate(
            avg=models.Avg('confidence_score')
        )['avg'] or 0
        avg_predicted_risk = predictions.aggregate(
            avg=models.Avg('predicted_overall_risk')
        )['avg'] or 0

        risk_improving = predictions.filter(risk_trend='improving').count()
        risk_stable = predictions.filter(risk_trend='stable').count()
        risk_deteriorating = predictions.filter(risk_trend='deteriorating').count()

        return {
            'total_predictions': total,
            'high_risk_count': high_risk,
            'inventory_pressure_count': inventory_pressure,
            'avg_confidence': round(avg_confidence, 1),
            'avg_predicted_risk': round(avg_predicted_risk, 1),
            'risk_improving': risk_improving,
            'risk_stable': risk_stable,
            'risk_deteriorating': risk_deteriorating,
        }

    @staticmethod
    def get_risk_distribution(horizon_days=7):
        today = date.today()
        predictions = GrainSituationPrediction.objects.filter(
            prediction_date=today,
            horizon_days=horizon_days
        ).values('predicted_risk_level').annotate(count=Count('id'))
        result = {'low': 0, 'medium': 0, 'high': 0}
        for item in predictions:
            result[item['predicted_risk_level']] = item['count']
        return result

    @staticmethod
    def get_inventory_distribution(horizon_days=7):
        today = date.today()
        predictions = GrainSituationPrediction.objects.filter(
            prediction_date=today,
            horizon_days=horizon_days
        ).select_related('granary')
        low = 0
        normal = 0
        high = 0
        for pred in predictions:
            capacity = pred.granary.capacity if pred.granary.capacity > 0 else 1
            ratio = (pred.predicted_inventory or pred.granary.current_stock) / capacity * 100
            if ratio < 20:
                low += 1
            elif ratio > 85:
                high += 1
            else:
                normal += 1
        return {'low': low, 'normal': normal, 'high': high}

    @staticmethod
    def get_prediction_trend(granary_id=None, horizon_days=7, days=14):
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
        query = GrainSituationPrediction.objects.filter(
            prediction_date__gte=start_date,
            prediction_date__lte=end_date,
            horizon_days=horizon_days
        ).select_related('granary').order_by('prediction_date')
        if granary_id and granary_id != 'all':
            query = query.filter(granary_id=granary_id)
        predictions = list(query)
        all_dates = [start_date + timedelta(days=i) for i in range(days)]
        if granary_id and granary_id != 'all':
            labels = [d.strftime('%m-%d') for d in all_dates]
            risk_scores = []
            for d in all_dates:
                p = next((x for x in predictions if x.prediction_date == d), None)
                risk_scores.append(p.predicted_overall_risk if p else None)
            return {'labels': labels, 'risk_scores': risk_scores}
        else:
            granaries = Granary.objects.filter(is_active=True)[:8]
            labels = [d.strftime('%m-%d') for d in all_dates]
            datasets = []
            for g in granaries:
                data = []
                for d in all_dates:
                    p = next((x for x in predictions if x.granary_id == g.id and x.prediction_date == d), None)
                    data.append(p.predicted_overall_risk if p else None)
                datasets.append({
                    'label': g.code,
                    'data': data,
                    'borderColor': f'rgba({(g.id * 40 + 100) % 255}, {(g.id * 60 + 80) % 255}, {(g.id * 90) % 255}, 1)',
                    'backgroundColor': f'rgba({(g.id * 40 + 100) % 255}, {(g.id * 60 + 80) % 255}, {(g.id * 90) % 255}, 0.1)',
                    'fill': False,
                    'tension': 0.3,
                })
            return {'labels': labels, 'lines': datasets}

    @staticmethod
    def get_inventory_turnover_stats(days=30):
        granaries = Granary.objects.filter(is_active=True)
        data = []
        for g in granaries:
            turnover = InventoryService.get_inventory_turnover(g, days)
            data.append({
                'id': g.id,
                'code': g.code,
                'name': g.name,
                'grain_type': g.grain_type.name,
                'current_stock': g.current_stock,
                'capacity': g.capacity,
                'ratio': round(g.current_stock / g.capacity * 100, 1) if g.capacity > 0 else 0,
                **turnover,
            })
        return sorted(data, key=lambda x: x['turnover_days'])

    @staticmethod
    def get_allocation_by_granary(days=30):
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        suggestions = AllocationSuggestion.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            status__in=['approved', 'executed']
        )
        result = {}
        for s in suggestions:
            qty = s.suggested_quantity
            source_id = s.source_granary_id
            target_id = s.target_granary_id
            if source_id not in result:
                result[source_id] = {
                    'id': source_id,
                    'code': s.source_granary.code,
                    'outbound': 0,
                    'inbound': 0,
                }
            result[source_id]['outbound'] += qty
            if target_id not in result:
                result[target_id] = {
                    'id': target_id,
                    'code': s.target_granary.code,
                    'outbound': 0,
                    'inbound': 0,
                }
            result[target_id]['inbound'] += qty
        return sorted(result.values(), key=lambda x: -(x['outbound'] + x['inbound']))


from django.db import models
from .models import (
    Region, TransportRoute, AllocationBatch, ExecutionNode,
    AbnormalLoss, ArrivalVerification
)


class BatchService:
    @staticmethod
    def _generate_batch_no():
        today = date.today()
        count = AllocationBatch.objects.filter(
            created_at__date=today
        ).count() + 1
        return f'PC{today.strftime("%Y%m%d")}{count:04d}'

    @classmethod
    def create_batch(cls, execution, quantity, route=None, operator=None, **kwargs):
        if quantity <= 0:
            raise ValueError('批次数量必须大于0')
        batch = AllocationBatch.objects.create(
            execution=execution,
            batch_no=cls._generate_batch_no(),
            quantity=quantity,
            route=route,
            operator=operator,
            **kwargs
        )
        return batch

    @classmethod
    def create_batches_from_execution(cls, execution, quantities, operator=None):
        total_qty = execution.suggestion.suggested_quantity
        sum_qty = sum(quantities)
        if abs(sum_qty - total_qty) > 0.01:
            raise ValueError(f'批次数量之和({sum_qty})必须等于调拨计划数量({total_qty})')
        batches = []
        route = execution.route
        for qty in quantities:
            batch = cls.create_batch(
                execution=execution,
                quantity=qty,
                route=route,
                operator=operator,
                transporter=execution.transporter,
                estimated_departure=execution.estimated_departure,
                estimated_arrival=execution.estimated_arrival,
            )
            batches.append(batch)
        return batches

    @classmethod
    def split_batch(cls, batch, split_quantities, operator=None):
        if batch.status not in ('pending', 'loading'):
            raise ValueError('只有待执行或装货中的批次才能拆分')
        sum_qty = sum(split_quantities)
        if abs(sum_qty - batch.quantity) > 0.01:
            raise ValueError(f'拆分数量之和({sum_qty})必须等于原批次数量({batch.quantity})')
        if len(split_quantities) < 2:
            raise ValueError('至少拆分为2个批次')

        batch.status = 'split'
        batch.save()

        child_batches = []
        for i, qty in enumerate(split_quantities):
            child = AllocationBatch.objects.create(
                execution=batch.execution,
                batch_no=f'{batch.batch_no}-{i + 1}',
                parent_batch=batch,
                quantity=qty,
                route=batch.route,
                operator=operator or batch.operator,
                transporter=batch.transporter,
                vehicle_no=batch.vehicle_no,
                driver=batch.driver,
                driver_phone=batch.driver_phone,
                estimated_departure=batch.estimated_departure,
                estimated_arrival=batch.estimated_arrival,
            )
            child_batches.append(child)
        return child_batches

    @classmethod
    def merge_batches(cls, batches, operator=None):
        if len(batches) < 2:
            raise ValueError('至少合并2个批次')
        execution_ids = set(b.execution_id for b in batches)
        if len(execution_ids) > 1:
            raise ValueError('只能合并同一调拨执行单下的批次')
        for b in batches:
            if b.status not in ('pending', 'loading'):
                raise ValueError(f'批次{b.batch_no}状态为{b.get_status_display()}，不能合并')

        execution = batches[0].execution
        total_qty = sum(b.quantity for b in batches)

        for b in batches:
            b.status = 'merged'
            b.save()

        merged_batch = AllocationBatch.objects.create(
            execution=execution,
            batch_no=f'{cls._generate_batch_no()}-M',
            quantity=total_qty,
            route=batches[0].route,
            operator=operator,
            transporter=batches[0].transporter,
        )
        return merged_batch

    @staticmethod
    def update_batch_status(batch, status, operator=None, **kwargs):
        batch.status = status
        now = timezone.now()
        if status == 'loading' and not batch.actual_departure:
            pass
        elif status == 'in_transit' and not batch.actual_departure:
            batch.actual_departure = now
        elif status == 'unloading' and not batch.actual_arrival:
            batch.actual_arrival = now
        elif status == 'completed':
            batch.completed_at = now
            if not batch.actual_arrival:
                batch.actual_arrival = now
            if not batch.actual_quantity:
                batch.actual_quantity = batch.quantity
        if operator:
            batch.operator = operator
        for key, value in kwargs.items():
            if hasattr(batch, key):
                setattr(batch, key, value)
        batch.save()
        return batch


class NodeTrackingService:
    @staticmethod
    def create_node(batch, node_type, node_name, node_order=0, **kwargs):
        node = ExecutionNode.objects.create(
            batch=batch,
            node_type=node_type,
            node_name=node_name,
            node_order=node_order,
            **kwargs
        )
        return node

    @classmethod
    def create_default_nodes(cls, batch):
        nodes = []
        source = batch.execution.suggestion.source_granary
        target = batch.execution.suggestion.target_granary

        departure_node = cls.create_node(
            batch=batch,
            node_type='departure',
            node_name=f'{source.code} 出发',
            node_order=1,
            granary=source,
            location=source.location,
            planned_time=batch.estimated_departure,
        )
        nodes.append(departure_node)

        if batch.route and batch.route.transport_type == 'multi':
            transit_node = cls.create_node(
                batch=batch,
                node_type='checkpoint',
                node_name='中转检查点',
                node_order=2,
            )
            nodes.append(transit_node)

        arrival_node = cls.create_node(
            batch=batch,
            node_type='arrival',
            node_name=f'{target.code} 到达',
            node_order=10,
            granary=target,
            location=target.location,
            planned_time=batch.estimated_arrival,
        )
        nodes.append(arrival_node)
        return nodes

    @staticmethod
    def complete_node(node, operator=None, **kwargs):
        node.is_completed = True
        node.actual_time = timezone.now()
        if operator:
            node.operator = operator
        for key, value in kwargs.items():
            if hasattr(node, key):
                setattr(node, key, value)
        node.save()
        return node

    @staticmethod
    def depart_node(node, operator=None):
        node.departed_time = timezone.now()
        if operator:
            node.operator = operator
        node.save()
        return node

    @staticmethod
    def get_batch_progress(batch):
        nodes = batch.nodes.all().order_by('node_order')
        if not nodes:
            return 0
        completed = nodes.filter(is_completed=True).count()
        return round(completed / nodes.count() * 100, 1)


class LossService:
    @staticmethod
    def report_loss(batch, loss_type, loss_quantity, description,
                    discovered_by=None, node=None, **kwargs):
        if loss_quantity <= 0:
            raise ValueError('损耗数量必须大于0')
        loss = AbnormalLoss.objects.create(
            batch=batch,
            node=node,
            loss_type=loss_type,
            loss_quantity=loss_quantity,
            description=description,
            discovered_by=discovered_by,
            **kwargs
        )
        return loss

    @staticmethod
    def investigate_loss(loss, cause_analysis, handled_by=None):
        loss.status = 'investigating'
        loss.cause_analysis = cause_analysis
        if handled_by:
            loss.handled_by = handled_by
        loss.save()
        return loss

    @staticmethod
    def confirm_loss(loss, actual_cost=None, confirmed_by=None, handling_result=None):
        loss.status = 'confirmed'
        if actual_cost is not None:
            loss.actual_cost = actual_cost
        if confirmed_by:
            loss.confirmed_by = confirmed_by
            loss.confirmed_time = timezone.now()
        if handling_result:
            loss.handling_result = handling_result
        loss.save()
        return loss

    @staticmethod
    def resolve_loss(loss, handling_measures, handled_by=None):
        loss.status = 'resolved'
        loss.handling_measures = handling_measures
        loss.handled_time = timezone.now()
        if handled_by:
            loss.handled_by = handled_by
        loss.save()
        return loss

    @staticmethod
    def close_loss(loss, remark=None):
        loss.status = 'closed'
        if remark:
            loss.remark = remark
        loss.save()
        return loss

    @staticmethod
    def get_batch_total_loss(batch):
        losses = batch.abnormal_losses.filter(status__in=['confirmed', 'resolved', 'closed'])
        return sum(l.loss_quantity for l in losses)

    @staticmethod
    def get_batch_total_loss_cost(batch):
        losses = batch.abnormal_losses.filter(status__in=['confirmed', 'resolved', 'closed'])
        return sum(l.actual_cost or l.estimated_cost for l in losses)


class ArrivalVerificationService:
    @staticmethod
    def _generate_verification_no():
        today = date.today()
        count = ArrivalVerification.objects.filter(
            created_at__date=today
        ).count() + 1
        return f'FH{today.strftime("%Y%m%d")}{count:04d}'

    @classmethod
    def create_verification(cls, batch, actual_received=None, **kwargs):
        if hasattr(batch, 'arrival_verification') and batch.arrival_verification:
            raise ValueError('该批次已存在到仓复核记录')
        verification = ArrivalVerification.objects.create(
            batch=batch,
            verification_no=cls._generate_verification_no(),
            planned_quantity=batch.quantity,
            actual_loaded=batch.actual_quantity or batch.quantity,
            actual_received=actual_received,
            **kwargs
        )
        return verification

    @staticmethod
    def start_verification(verification, verifier=None):
        verification.status = 'verifying'
        if verifier:
            verification.verifier = verifier
        verification.save()
        return verification

    @staticmethod
    def verify(verification, actual_received, quality_check_passed=True,
               verifier=None, **kwargs):
        verification.actual_received = actual_received
        planned = verification.planned_quantity
        loaded = verification.actual_loaded or planned
        verification.quantity_diff = actual_received - loaded
        verification.quality_check_passed = quality_check_passed
        verification.verification_time = timezone.now()
        if verifier:
            verification.verifier = verifier
        for key, value in kwargs.items():
            if hasattr(verification, key):
                setattr(verification, key, value)

        diff_rate = verification.get_diff_rate()
        if not quality_check_passed:
            verification.status = 'failed'
        elif diff_rate > 2:
            verification.status = 'discrepancy'
        else:
            verification.status = 'passed'
        verification.save()
        return verification

    @staticmethod
    def confirm_verification(verification, confirmed_by, handling_suggestion=None):
        if handling_suggestion:
            verification.handling_suggestion = handling_suggestion
        verification.confirmed_by = confirmed_by
        verification.confirmed_time = timezone.now()
        verification.save()
        return verification


class CollaborativeAnalyticsService:
    @staticmethod
    def get_timeliness_stats(days=30, start_date=None, end_date=None):
        end_date = end_date or date.today()
        start_date = start_date or (end_date - timedelta(days=days - 1))

        batches = AllocationBatch.objects.filter(
            status='completed',
            completed_at__date__gte=start_date,
            completed_at__date__lte=end_date
        ).select_related('route', 'execution__suggestion__source_granary',
                          'execution__suggestion__target_granary')

        total = batches.count()
        on_time_count = 0
        delayed_count = 0
        total_estimated_hours = 0
        total_actual_hours = 0
        total_delay_hours = 0

        for b in batches:
            transit = b.get_transit_hours()
            estimated = b.route.estimated_hours if b.route else 0
            if transit and estimated > 0:
                total_estimated_hours += estimated
                total_actual_hours += transit
                if transit <= estimated * 1.1:
                    on_time_count += 1
                else:
                    delayed_count += 1
                    total_delay_hours += (transit - estimated)

        return {
            'total_completed': total,
            'on_time_count': on_time_count,
            'delayed_count': delayed_count,
            'on_time_rate': round(on_time_count / total * 100, 1) if total > 0 else 0,
            'avg_estimated_hours': round(total_estimated_hours / total, 2) if total > 0 else 0,
            'avg_actual_hours': round(total_actual_hours / total, 2) if total > 0 else 0,
            'avg_delay_hours': round(total_delay_hours / delayed_count, 2) if delayed_count > 0 else 0,
            'total_delay_hours': round(total_delay_hours, 2),
        }

    @staticmethod
    def get_loss_rate_stats(days=30, start_date=None, end_date=None):
        end_date = end_date or date.today()
        start_date = start_date or (end_date - timedelta(days=days - 1))

        batches = AllocationBatch.objects.filter(
            status='completed',
            completed_at__date__gte=start_date,
            completed_at__date__lte=end_date
        )

        total_quantity = 0
        total_loss = 0
        batches_with_loss = 0
        loss_by_type = {}

        for b in batches:
            actual = b.actual_quantity or b.quantity
            total_quantity += actual
            batch_loss = b.loss_quantity or 0
            total_loss += batch_loss
            if batch_loss > 0:
                batches_with_loss += 1

        losses = AbnormalLoss.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        for l in losses:
            t = l.get_loss_type_display()
            loss_by_type[t] = loss_by_type.get(t, 0) + l.loss_quantity

        return {
            'total_completed_batches': batches.count(),
            'total_quantity': round(total_quantity, 2),
            'total_loss': round(total_loss, 2),
            'overall_loss_rate': round(total_loss / total_quantity * 100, 3) if total_quantity > 0 else 0,
            'batches_with_loss': batches_with_loss,
            'loss_occurrence_rate': round(batches_with_loss / batches.count() * 100, 1) if batches.count() > 0 else 0,
            'loss_by_type': loss_by_type,
        }

    @staticmethod
    def get_execution_rate_stats(days=30, start_date=None, end_date=None):
        end_date = end_date or date.today()
        start_date = start_date or (end_date - timedelta(days=days - 1))

        suggestions = AllocationSuggestion.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        executions = AllocationExecution.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )

        total_suggestions = suggestions.count()
        approved = suggestions.filter(status__in=['approved', 'executed']).count()
        rejected = suggestions.filter(status='rejected').count()
        total_executions = executions.count()
        completed_executions = executions.filter(status='completed').count()
        cancelled_executions = executions.filter(status='cancelled').count()

        total_planned_qty = sum(s.suggested_quantity for s in suggestions.filter(status__in=['approved', 'executed']))
        total_actual_qty = sum(
            e.actual_quantity or 0 for e in executions.filter(status='completed')
        )

        return {
            'total_suggestions': total_suggestions,
            'approved_suggestions': approved,
            'rejected_suggestions': rejected,
            'approval_rate': round(approved / total_suggestions * 100, 1) if total_suggestions > 0 else 0,
            'total_executions': total_executions,
            'completed_executions': completed_executions,
            'cancelled_executions': cancelled_executions,
            'execution_completion_rate': round(completed_executions / total_executions * 100, 1) if total_executions > 0 else 0,
            'total_planned_quantity': round(total_planned_qty, 2),
            'total_actual_quantity': round(total_actual_qty, 2),
            'quantity_achievement_rate': round(total_actual_qty / total_planned_qty * 100, 1) if total_planned_qty > 0 else 0,
        }

    @staticmethod
    def get_collaboration_efficiency(days=30, start_date=None, end_date=None):
        end_date = end_date or date.today()
        start_date = start_date or (end_date - timedelta(days=days - 1))

        executions = AllocationExecution.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).select_related('suggestion__source_granary', 'suggestion__target_granary')

        total_executions = executions.count()
        completed = executions.filter(status='completed')
        completed_count = completed.count()

        total_cycle_hours = 0
        verified_count = 0
        verification_pass_count = 0
        cross_region_count = 0
        cross_region_completed = 0

        for e in completed:
            if e.created_at and e.completed_at:
                delta = e.completed_at - e.created_at
                total_cycle_hours += delta.total_seconds() / 3600

            source_region = e.suggestion.source_granary.region_id
            target_region = e.suggestion.target_granary.region_id
            if source_region and target_region and source_region != target_region:
                cross_region_count += 1
                if e.status == 'completed':
                    cross_region_completed += 1

            for b in e.batches.filter(status='completed'):
                if hasattr(b, 'arrival_verification') and b.arrival_verification:
                    verified_count += 1
                    if b.arrival_verification.status == 'passed':
                        verification_pass_count += 1

        batch_total = AllocationBatch.objects.filter(
            execution__in=executions
        ).count()
        batch_completed = AllocationBatch.objects.filter(
            execution__in=executions,
            status='completed'
        ).count()

        return {
            'total_executions': total_executions,
            'completed_executions': completed_count,
            'execution_rate': round(completed_count / total_executions * 100, 1) if total_executions > 0 else 0,
            'avg_cycle_hours': round(total_cycle_hours / completed_count, 2) if completed_count > 0 else 0,
            'total_batches': batch_total,
            'completed_batches': batch_completed,
            'batch_completion_rate': round(batch_completed / batch_total * 100, 1) if batch_total > 0 else 0,
            'verified_batches': verified_count,
            'verification_rate': round(verified_count / batch_completed * 100, 1) if batch_completed > 0 else 0,
            'verification_pass_count': verification_pass_count,
            'verification_pass_rate': round(verification_pass_count / verified_count * 100, 1) if verified_count > 0 else 0,
            'cross_region_executions': cross_region_count,
            'cross_region_completion_rate': round(
                cross_region_completed / cross_region_count * 100, 1
            ) if cross_region_count > 0 else 0,
        }

    @staticmethod
    def get_region_collaboration_stats(days=30):
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        executions = AllocationExecution.objects.filter(
            status='completed',
            completed_at__date__gte=start_date,
            completed_at__date__lte=end_date
        ).select_related('suggestion__source_granary__region',
                         'suggestion__target_granary__region')

        region_stats = {}
        for e in executions:
            src = e.suggestion.source_granary.region
            tgt = e.suggestion.target_granary.region
            if not src or not tgt:
                continue
            key = f'{src.name}→{tgt.name}'
            if key not in region_stats:
                region_stats[key] = {
                    'source_region': src.name,
                    'target_region': tgt.name,
                    'count': 0,
                    'quantity': 0,
                    'avg_hours': 0,
                    'hours': [],
                }
            region_stats[key]['count'] += 1
            region_stats[key]['quantity'] += e.actual_quantity or e.suggestion.suggested_quantity
            transit = e.get_transit_hours()
            if transit:
                region_stats[key]['hours'].append(transit)

        result = []
        for key, stats in region_stats.items():
            if stats['hours']:
                stats['avg_hours'] = round(sum(stats['hours']) / len(stats['hours']), 2)
            del stats['hours']
            stats['quantity'] = round(stats['quantity'], 2)
            result.append(stats)
        return sorted(result, key=lambda x: -x['count'])

    @staticmethod
    def get_transport_route_stats(days=30):
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        batches = AllocationBatch.objects.filter(
            status='completed',
            completed_at__date__gte=start_date,
            completed_at__date__lte=end_date,
            route__isnull=False
        ).select_related('route')

        route_stats = {}
        for b in batches:
            r = b.route
            key = f'{r.source_granary.code}→{r.target_granary.code}({r.get_transport_type_display()})'
            if key not in route_stats:
                route_stats[key] = {
                    'route': key,
                    'transport_type': r.get_transport_type_display(),
                    'count': 0,
                    'quantity': 0,
                    'estimated_hours': r.estimated_hours,
                    'actual_hours': [],
                }
            route_stats[key]['count'] += 1
            route_stats[key]['quantity'] += b.actual_quantity or b.quantity
            transit = b.get_transit_hours()
            if transit:
                route_stats[key]['actual_hours'].append(transit)

        result = []
        for key, stats in route_stats.items():
            if stats['actual_hours']:
                stats['avg_actual_hours'] = round(sum(stats['actual_hours']) / len(stats['actual_hours']), 2)
                stats['efficiency_rate'] = round(
                    stats['estimated_hours'] / stats['avg_actual_hours'] * 100, 1
                ) if stats['avg_actual_hours'] > 0 else 0
            else:
                stats['avg_actual_hours'] = 0
                stats['efficiency_rate'] = 0
            del stats['actual_hours']
            stats['quantity'] = round(stats['quantity'], 2)
            result.append(stats)
        return sorted(result, key=lambda x: -x['count'])
