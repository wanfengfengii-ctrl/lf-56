from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Count, Q
from .models import (
    GrainType, Granary, TemperatureHumidityLog,
    VentilationLog, PestInspection, RiskAssessment,
    Warning, DisposalTask, DisposalProgressLog, WarningNotifyLog
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
