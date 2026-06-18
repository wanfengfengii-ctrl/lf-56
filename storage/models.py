from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta, datetime


class GrainType(models.Model):
    name = models.CharField('粮食品类名称', max_length=50, unique=True)
    safe_temp_min = models.FloatField('安全温度下限(℃)', default=10.0)
    safe_temp_max = models.FloatField('安全温度上限(℃)', default=25.0)
    safe_humidity_min = models.FloatField('安全湿度下限(%)', default=50.0)
    safe_humidity_max = models.FloatField('安全湿度上限(%)', default=75.0)
    mold_sensitivity = models.FloatField('霉变敏感性系数', default=1.0,
                                        help_text='数值越大越容易霉变')
    pest_sensitivity = models.FloatField('虫害敏感性系数', default=1.0,
                                         help_text='数值越大越容易生虫')
    description = models.TextField('备注', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'grain_type'
        verbose_name = '粮食品类'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Granary(models.Model):
    VENTILATION_CHOICES = (
        ('closed', '关闭'),
        ('natural', '自然通风'),
        ('mechanical', '机械通风'),
    )

    code = models.CharField('粮仓编号', max_length=20, unique=True)
    name = models.CharField('粮仓名称', max_length=100)
    region = models.ForeignKey('Region', on_delete=models.SET_NULL, blank=True, null=True,
                               verbose_name='所属区域', related_name='granaries')
    capacity = models.FloatField('设计容量(吨)', default=0.0)
    current_stock = models.FloatField('当前库存(吨)', default=0.0)
    grain_type = models.ForeignKey(GrainType, on_delete=models.PROTECT,
                                   verbose_name='储粮种类', related_name='granaries')
    location = models.CharField('位置', max_length=200, blank=True, null=True)
    latitude = models.FloatField('纬度', blank=True, null=True)
    longitude = models.FloatField('经度', blank=True, null=True)
    ventilation_status = models.CharField('通风状态', max_length=20,
                                          choices=VENTILATION_CHOICES, default='closed')
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'granary'
        verbose_name = '粮仓'
        verbose_name_plural = verbose_name
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.name}'

    def get_consecutive_days(self):
        logs = TemperatureHumidityLog.objects.filter(
            granary=self
        ).order_by('-record_date').values_list('record_date', flat=True)
        if not logs:
            return 0
        dates = list(logs)
        count = 1
        for i in range(1, len(dates)):
            if (dates[i - 1] - dates[i]).days == 1:
                count += 1
            else:
                break
        return count

    def has_continuous_data(self, days=3):
        return self.get_consecutive_days() >= days


class TemperatureHumidityLog(models.Model):
    granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                verbose_name='粮仓', related_name='th_logs')
    record_date = models.DateField('记录日期')
    temperature = models.FloatField('温度(℃)')
    humidity = models.FloatField('相对湿度(%)')
    recorder = models.CharField('记录人', max_length=50, blank=True, null=True)
    remark = models.TextField('备注', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'temperature_humidity_log'
        verbose_name = '温湿度记录'
        verbose_name_plural = verbose_name
        unique_together = ('granary', 'record_date')
        ordering = ['-record_date']

    def __str__(self):
        return f'{self.granary.code} {self.record_date} T:{self.temperature}℃ H:{self.humidity}%'

    def clean(self):
        if self.temperature is not None and (self.temperature < -40 or self.temperature > 60):
            raise ValidationError({'temperature': '温度值超出合理范围(-40℃ ~ 60℃)'})
        if self.humidity is not None and (self.humidity < 0 or self.humidity > 100):
            raise ValidationError({'humidity': '湿度值超出合理范围(0% ~ 100%)'})


class VentilationLog(models.Model):
    VENTILATION_TYPE_CHOICES = (
        ('natural', '自然通风'),
        ('mechanical', '机械通风'),
    )

    granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                verbose_name='粮仓', related_name='ventilation_logs')
    start_time = models.DateTimeField('开始时间')
    end_time = models.DateTimeField('结束时间', blank=True, null=True)
    ventilation_type = models.CharField('通风类型', max_length=20,
                                        choices=VENTILATION_TYPE_CHOICES)
    operator = models.CharField('操作人', max_length=50, blank=True, null=True)
    before_temp = models.FloatField('通风前温度(℃)', blank=True, null=True)
    before_humidity = models.FloatField('通风前湿度(%)', blank=True, null=True)
    after_temp = models.FloatField('通风后温度(℃)', blank=True, null=True)
    after_humidity = models.FloatField('通风后湿度(%)', blank=True, null=True)
    remark = models.TextField('备注', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'ventilation_log'
        verbose_name = '通风记录'
        verbose_name_plural = verbose_name
        ordering = ['-start_time']

    def __str__(self):
        return f'{self.granary.code} {self.get_ventilation_type_display()} {self.start_time}'

    def get_duration_hours(self):
        if self.end_time:
            delta = self.end_time - self.start_time
            return round(delta.total_seconds() / 3600, 2)
        return None

    def clean(self):
        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValidationError({'end_time': '结束时间不能早于开始时间'})


class PestInspection(models.Model):
    granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                verbose_name='粮仓', related_name='pest_inspections')
    inspect_date = models.DateField('检查日期')
    pest_density = models.FloatField('虫害密度(头/公斤)')
    pest_type = models.CharField('虫害种类', max_length=100, blank=True, null=True)
    sample_points = models.IntegerField('取样点数', default=5)
    inspector = models.CharField('检查人', max_length=50, blank=True, null=True)
    remark = models.TextField('备注', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'pest_inspection'
        verbose_name = '虫害抽检记录'
        verbose_name_plural = verbose_name
        ordering = ['-inspect_date']

    def __str__(self):
        return f'{self.granary.code} {self.inspect_date} 密度:{self.pest_density}'

    def clean(self):
        if self.pest_density is not None and self.pest_density < 0:
            raise ValidationError({'pest_density': '虫害密度不能为负数'})
        if self.sample_points is not None and self.sample_points < 1:
            raise ValidationError({'sample_points': '取样点数至少为1'})


class RiskAssessment(models.Model):
    RISK_LEVEL_CHOICES = (
        ('low', '低风险'),
        ('medium', '中风险'),
        ('high', '高风险'),
    )
    STATUS_CHOICES = (
        ('pending', '待处理'),
        ('processed', '已处理'),
    )

    granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                verbose_name='粮仓', related_name='risk_assessments')
    assess_date = models.DateField('评估日期')
    mold_risk_score = models.FloatField('霉变风险评分(0-100)', default=0.0)
    pest_risk_score = models.FloatField('虫害扩散风险评分(0-100)', default=0.0)
    ventilation_factor = models.FloatField('通风系数', default=1.0)
    overall_risk_score = models.FloatField('综合风险评分(0-100)', default=0.0)
    risk_level = models.CharField('风险等级', max_length=20, choices=RISK_LEVEL_CHOICES, default='low')
    is_formal = models.BooleanField('是否正式结论', default=False)
    consecutive_days = models.IntegerField('连续监测天数', default=0)
    status = models.CharField('处理状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    disposal_suggestion = models.TextField('处置建议', blank=True, null=True)
    disposal_person = models.CharField('处置人', max_length=50, blank=True, null=True)
    disposal_date = models.DateField('处置日期', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'risk_assessment'
        verbose_name = '风险评估'
        verbose_name_plural = verbose_name
        ordering = ['-assess_date', '-overall_risk_score']

    def __str__(self):
        return f'{self.granary.code} {self.assess_date} {self.get_risk_level_display()}'

    def clean(self):
        if self.status == 'processed' and self.risk_level == 'high' and not self.disposal_suggestion:
            raise ValidationError({'disposal_suggestion': '高风险粮仓必须填写处置建议才能标记为已处理'})

    @staticmethod
    def calculate_ventilation_factor(granary, assess_date):
        recent_vent = VentilationLog.objects.filter(
            granary=granary,
            start_time__date__lte=assess_date,
            start_time__date__gte=assess_date - timedelta(days=3)
        ).order_by('-start_time').first()

        if recent_vent:
            duration = recent_vent.get_duration_hours()
            if duration is None:
                return 0.9
            if recent_vent.ventilation_type == 'mechanical':
                if duration >= 4:
                    return 0.6
                elif duration >= 2:
                    return 0.7
                else:
                    return 0.85
            else:
                if duration >= 8:
                    return 0.7
                elif duration >= 4:
                    return 0.8
                else:
                    return 0.95

        status = granary.ventilation_status
        if status == 'mechanical':
            return 0.8
        elif status == 'natural':
            return 0.95
        else:
            return 1.2


class Warning(models.Model):
    LEVEL_CHOICES = (
        ('level1', '一级预警（红色）'),
        ('level2', '二级预警（橙色）'),
        ('level3', '三级预警（黄色）'),
    )
    TRIGGER_TYPE_CHOICES = (
        ('auto', '自动触发'),
        ('manual', '手动触发'),
    )
    NOTIFY_METHOD_CHOICES = (
        ('system', '系统消息'),
        ('sms', '短信通知'),
        ('email', '邮件通知'),
        ('all', '全部方式'),
    )
    STATUS_CHOICES = (
        ('pending', '待处置'),
        ('processing', '处置中'),
        ('reviewing', '待复查'),
        ('closed', '已闭环'),
    )

    granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                verbose_name='预警粮仓', related_name='warnings')
    risk_assessment = models.ForeignKey(RiskAssessment, on_delete=models.SET_NULL,
                                        verbose_name='关联风险评估', related_name='warnings',
                                        blank=True, null=True)
    warning_level = models.CharField('预警等级', max_length=20, choices=LEVEL_CHOICES)
    trigger_type = models.CharField('触发方式', max_length=20, choices=TRIGGER_TYPE_CHOICES, default='auto')
    notify_method = models.CharField('通知方式', max_length=20, choices=NOTIFY_METHOD_CHOICES, default='system')
    warning_time = models.DateTimeField('预警时间', default=timezone.now)
    warning_content = models.TextField('预警内容')
    status = models.CharField('预警状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    notified_person = models.CharField('被通知人', max_length=100, blank=True, null=True)
    is_overdue = models.BooleanField('是否超时', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'warning'
        verbose_name = '预警记录'
        verbose_name_plural = verbose_name
        ordering = ['-warning_time']

    def __str__(self):
        return f'{self.granary.code} {self.get_warning_level_display()} {self.warning_time}'

    def clean(self):
        if self.status == 'closed' and not self.disposal_tasks.filter(status='closed').exists():
            pass

    @staticmethod
    def get_level_from_risk(risk_level):
        if risk_level == 'high':
            return 'level1'
        elif risk_level == 'medium':
            return 'level2'
        else:
            return 'level3'

    def get_deadline_hours(self):
        if self.warning_level == 'level1':
            return 2
        elif self.warning_level == 'level2':
            return 8
        else:
            return 24

    def check_overdue(self):
        if self.status in ('closed',):
            return False
        deadline = self.warning_time + timedelta(hours=self.get_deadline_hours())
        return timezone.now() > deadline


class DisposalTask(models.Model):
    PRIORITY_CHOICES = (
        ('urgent', '紧急'),
        ('high', '高'),
        ('normal', '普通'),
    )
    STATUS_CHOICES = (
        ('assigned', '已分派'),
        ('in_progress', '处理中'),
        ('submitted', '待复查'),
        ('review_failed', '复查不通过'),
        ('closed', '已闭环'),
    )

    warning = models.ForeignKey(Warning, on_delete=models.CASCADE,
                                verbose_name='关联预警', related_name='disposal_tasks')
    task_title = models.CharField('任务标题', max_length=200)
    task_description = models.TextField('任务描述', blank=True, null=True)
    assignee = models.CharField('处置负责人', max_length=100)
    assigner = models.CharField('任务分派人', max_length=100, blank=True, null=True)
    assigned_time = models.DateTimeField('分派时间', default=timezone.now)
    deadline = models.DateTimeField('要求完成时间')
    priority = models.CharField('优先级', max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField('任务状态', max_length=20, choices=STATUS_CHOICES, default='assigned')
    progress = models.IntegerField('处理进度(%)', default=0)
    disposal_measures = models.TextField('处置措施', blank=True, null=True)
    disposal_result = models.TextField('处置结果', blank=True, null=True)
    disposal_attachment = models.TextField('附件说明', blank=True, null=True)
    completed_time = models.DateTimeField('实际完成时间', blank=True, null=True)
    reviewer = models.CharField('复查人', max_length=100, blank=True, null=True)
    review_time = models.DateTimeField('复查时间', blank=True, null=True)
    review_opinion = models.TextField('复查意见', blank=True, null=True)
    review_passed = models.BooleanField('复查是否通过', default=False)
    archived_by = models.CharField('归档人', max_length=100, blank=True, null=True)
    archived_time = models.DateTimeField('归档时间', blank=True, null=True)
    archive_remark = models.TextField('归档备注', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'disposal_task'
        verbose_name = '处置任务'
        verbose_name_plural = verbose_name
        ordering = ['-assigned_time']

    def __str__(self):
        return f'{self.task_title} - {self.assignee}'

    def clean(self):
        if self.progress is not None and (self.progress < 0 or self.progress > 100):
            raise ValidationError({'progress': '进度必须在0-100之间'})
        if self.deadline and self.assigned_time and self.deadline < self.assigned_time:
            raise ValidationError({'deadline': '完成时间不能早于分派时间'})
        if self.status == 'closed' and not self.review_passed:
            raise ValidationError({'status': '未通过复查的任务不能闭环'})

    def is_overdue(self):
        if self.status in ('closed',):
            return False
        if self.completed_time:
            return self.completed_time > self.deadline
        return timezone.now() > self.deadline

    def get_remaining_hours(self):
        if self.status == 'closed':
            return 0
        now = timezone.now()
        if now >= self.deadline:
            return 0
        delta = self.deadline - now
        return round(delta.total_seconds() / 3600, 1)


class DisposalProgressLog(models.Model):
    task = models.ForeignKey(DisposalTask, on_delete=models.CASCADE,
                             verbose_name='处置任务', related_name='progress_logs')
    progress_percent = models.IntegerField('当前进度(%)')
    progress_description = models.TextField('进度说明')
    operator = models.CharField('操作人', max_length=100)
    operate_time = models.DateTimeField('操作时间', default=timezone.now)
    remark = models.TextField('备注', blank=True, null=True)

    class Meta:
        db_table = 'disposal_progress_log'
        verbose_name = '处置进度记录'
        verbose_name_plural = verbose_name
        ordering = ['-operate_time']

    def __str__(self):
        return f'{self.task.task_title} - {self.progress_percent}%'


class WarningNotifyLog(models.Model):
    warning = models.ForeignKey(Warning, on_delete=models.CASCADE,
                                verbose_name='预警', related_name='notify_logs')
    notify_method = models.CharField('通知方式', max_length=20)
    notify_target = models.CharField('通知对象', max_length=200)
    notify_content = models.TextField('通知内容')
    notify_time = models.DateTimeField('通知时间', default=timezone.now)
    is_success = models.BooleanField('是否成功', default=True)
    fail_reason = models.TextField('失败原因', blank=True, null=True)

    class Meta:
        db_table = 'warning_notify_log'
        verbose_name = '预警通知记录'
        verbose_name_plural = verbose_name
        ordering = ['-notify_time']

    def __str__(self):
        return f'{self.warning} - {self.notify_method}'


class InventoryChangeLog(models.Model):
    CHANGE_TYPE_CHOICES = (
        ('in', '入库'),
        ('out', '出库'),
        ('transfer_in', '调拨入库'),
        ('transfer_out', '调拨出库'),
        ('adjust', '库存调整'),
    )

    granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                verbose_name='粮仓', related_name='inventory_changes')
    change_date = models.DateField('变动日期')
    change_type = models.CharField('变动类型', max_length=20, choices=CHANGE_TYPE_CHOICES)
    quantity = models.FloatField('变动数量(吨)')
    balance_after = models.FloatField('变动后库存(吨)')
    grain_type = models.ForeignKey(GrainType, on_delete=models.PROTECT,
                                   verbose_name='粮食品类', related_name='inventory_changes')
    operator = models.CharField('操作人', max_length=50, blank=True, null=True)
    remark = models.TextField('备注', blank=True, null=True)
    related_allocation = models.ForeignKey('AllocationExecution', on_delete=models.SET_NULL,
                                           verbose_name='关联调拨单', blank=True, null=True,
                                           related_name='inventory_logs')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'inventory_change_log'
        verbose_name = '库存变动记录'
        verbose_name_plural = verbose_name
        ordering = ['-change_date', '-created_at']

    def __str__(self):
        return f'{self.granary.code} {self.get_change_type_display()} {self.quantity}吨'

    def clean(self):
        if self.quantity is not None and self.quantity == 0:
            raise ValidationError({'quantity': '变动数量不能为0'})
        if self.balance_after is not None and self.balance_after < 0:
            raise ValidationError({'balance_after': '变动后库存不能为负数'})


class GrainSituationPrediction(models.Model):
    PREDICTION_HORIZON_CHOICES = (
        (7, '7天'),
        (14, '14天'),
        (30, '30天'),
    )
    TREND_CHOICES = (
        ('improving', '好转'),
        ('stable', '稳定'),
        ('deteriorating', '恶化'),
    )

    granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                verbose_name='粮仓', related_name='predictions')
    prediction_date = models.DateField('预测日期')
    horizon_days = models.IntegerField('预测周期(天)', choices=PREDICTION_HORIZON_CHOICES, default=7)
    target_date = models.DateField('预测目标日期')

    predicted_temp = models.FloatField('预测温度(℃)', blank=True, null=True)
    predicted_humidity = models.FloatField('预测湿度(%)', blank=True, null=True)
    predicted_pest_density = models.FloatField('预测虫害密度(头/公斤)', blank=True, null=True)
    predicted_mold_risk = models.FloatField('预测霉变风险评分', default=0.0)
    predicted_pest_risk = models.FloatField('预测虫害风险评分', default=0.0)
    predicted_overall_risk = models.FloatField('预测综合风险评分', default=0.0)
    predicted_risk_level = models.CharField('预测风险等级', max_length=20,
                                             choices=RiskAssessment.RISK_LEVEL_CHOICES, default='low')
    predicted_inventory = models.FloatField('预测库存(吨)', blank=True, null=True)

    temp_trend = models.CharField('温度趋势', max_length=20, choices=TREND_CHOICES, default='stable')
    humidity_trend = models.CharField('湿度趋势', max_length=20, choices=TREND_CHOICES, default='stable')
    risk_trend = models.CharField('风险趋势', max_length=20, choices=TREND_CHOICES, default='stable')
    inventory_trend = models.CharField('库存趋势', max_length=20, choices=TREND_CHOICES, default='stable')

    confidence_score = models.FloatField('预测置信度(0-100)', default=80.0)
    is_high_risk = models.BooleanField('是否高风险预警', default=False)
    is_inventory_pressure = models.BooleanField('是否库存压力', default=False)
    warning_message = models.TextField('预警提示', blank=True, null=True)

    model_version = models.CharField('预测模型版本', max_length=50, default='v1.0')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'grain_situation_prediction'
        verbose_name = '粮情预测'
        verbose_name_plural = verbose_name
        unique_together = ('granary', 'prediction_date', 'horizon_days', 'target_date')
        ordering = ['-prediction_date', '-created_at']

    def __str__(self):
        return f'{self.granary.code} {self.prediction_date} 预测{self.horizon_days}天'

    def clean(self):
        if self.confidence_score is not None:
            if self.confidence_score < 0 or self.confidence_score > 100:
                raise ValidationError({'confidence_score': '置信度必须在0-100之间'})


class AllocationConfig(models.Model):
    PRIORITY_RULE_CHOICES = (
        ('risk_first', '风险优先'),
        ('inventory_first', '库存优先'),
        ('distance_first', '距离优先'),
        ('balanced', '综合平衡'),
    )

    name = models.CharField('配置名称', max_length=100, unique=True)
    description = models.TextField('配置描述', blank=True, null=True)
    is_default = models.BooleanField('是否默认配置', default=False)

    safety_stock_ratio = models.FloatField('安全库存比例(%)', default=30.0,
                                           help_text='相对于设计容量的安全库存比例')
    min_transfer_quantity = models.FloatField('最小调拨数量(吨)', default=10.0)
    max_transfer_quantity = models.FloatField('最大调拨数量(吨)', default=500.0)
    priority_rule = models.CharField('调拨优先级规则', max_length=30,
                                     choices=PRIORITY_RULE_CHOICES, default='balanced')
    risk_weight = models.FloatField('风险权重', default=0.4, help_text='0-1之间')
    inventory_weight = models.FloatField('库存权重', default=0.4, help_text='0-1之间')
    distance_weight = models.FloatField('距离权重', default=0.2, help_text='0-1之间')

    high_risk_threshold = models.FloatField('高风险阈值', default=70.0,
                                            help_text='综合风险评分高于此值视为高风险')
    low_inventory_threshold = models.FloatField('低库存阈值(%)', default=20.0,
                                                help_text='库存占容量比例低于此值视为库存不足')
    high_inventory_threshold = models.FloatField('高库存阈值(%)', default=85.0,
                                                 help_text='库存占容量比例高于此值视为库存过高')

    allow_cross_grain_type = models.BooleanField('允许跨品类调拨', default=False)
    auto_approve_below = models.FloatField('自动审批阈值(吨)', default=50.0,
                                           help_text='低于此数量的调拨建议自动批准')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'allocation_config'
        verbose_name = '调拨配置'
        verbose_name_plural = verbose_name
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f'{self.name}{"(默认)" if self.is_default else ""}'

    def clean(self):
        total_weight = (self.risk_weight or 0) + (self.inventory_weight or 0) + (self.distance_weight or 0)
        if abs(total_weight - 1.0) > 0.01:
            raise ValidationError('风险、库存、距离权重之和必须等于1')
        if self.low_inventory_threshold >= self.high_inventory_threshold:
            raise ValidationError({'low_inventory_threshold': '低库存阈值必须小于高库存阈值'})
        if self.min_transfer_quantity >= self.max_transfer_quantity:
            raise ValidationError({'min_transfer_quantity': '最小调拨数量必须小于最大调拨数量'})


class AllocationSuggestion(models.Model):
    STATUS_CHOICES = (
        ('pending', '待审核'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
        ('executed', '已执行'),
        ('cancelled', '已取消'),
    )

    source_granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                       verbose_name='源粮仓', related_name='outbound_suggestions')
    target_granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                       verbose_name='目标粮仓', related_name='inbound_suggestions')
    grain_type = models.ForeignKey(GrainType, on_delete=models.PROTECT,
                                   verbose_name='粮食品类', related_name='allocation_suggestions')

    suggested_quantity = models.FloatField('建议调拨数量(吨)')
    priority_score = models.FloatField('优先级评分(0-100)', default=0.0)
    priority_level = models.CharField('优先级', max_length=20,
                                       choices=DisposalTask.PRIORITY_CHOICES, default='normal')
    reason = models.TextField('调拨原因')
    expected_benefit = models.TextField('预期效益', blank=True, null=True)

    source_risk_score = models.FloatField('源仓风险评分', default=0.0)
    target_risk_score = models.FloatField('目标仓风险评分', default=0.0)
    source_inventory_ratio = models.FloatField('源仓库存占比(%)', default=0.0)
    target_inventory_ratio = models.FloatField('目标仓库存占比(%)', default=0.0)

    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    config = models.ForeignKey(AllocationConfig, on_delete=models.SET_NULL,
                               verbose_name='使用配置', blank=True, null=True)
    prediction = models.ForeignKey(GrainSituationPrediction, on_delete=models.SET_NULL,
                                    verbose_name='关联预测', blank=True, null=True)

    approved_by = models.CharField('审批人', max_length=50, blank=True, null=True)
    approved_at = models.DateTimeField('审批时间', blank=True, null=True)
    approval_opinion = models.TextField('审批意见', blank=True, null=True)

    created_by = models.CharField('创建人', max_length=50, default='系统')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'allocation_suggestion'
        verbose_name = '调拨建议'
        verbose_name_plural = verbose_name
        ordering = ['-priority_score', '-created_at']

    def __str__(self):
        return f'{self.source_granary.code}→{self.target_granary.code} {self.suggested_quantity}吨'

    def clean(self):
        if self.source_granary_id == self.target_granary_id:
            raise ValidationError({'target_granary': '目标粮仓不能与源粮仓相同'})
        if self.suggested_quantity <= 0:
            raise ValidationError({'suggested_quantity': '调拨数量必须大于0'})


class Region(models.Model):
    code = models.CharField('区域编号', max_length=20, unique=True)
    name = models.CharField('区域名称', max_length=100)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True,
                               verbose_name='上级区域', related_name='children')
    description = models.TextField('描述', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'region'
        verbose_name = '区域'
        verbose_name_plural = verbose_name
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.name}'


class TransportRoute(models.Model):
    TRANSPORT_TYPE_CHOICES = (
        ('road', '公路运输'),
        ('rail', '铁路运输'),
        ('water', '水路运输'),
        ('multi', '多式联运'),
    )

    source_granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                       verbose_name='起点粮仓', related_name='outbound_routes')
    target_granary = models.ForeignKey(Granary, on_delete=models.CASCADE,
                                       verbose_name='终点粮仓', related_name='inbound_routes')
    transport_type = models.CharField('运输方式', max_length=20, choices=TRANSPORT_TYPE_CHOICES, default='road')
    distance_km = models.FloatField('运输距离(公里)', default=0.0)
    estimated_hours = models.FloatField('预计运输时长(小时)', default=0.0)
    cost_per_ton = models.FloatField('单位运费(元/吨)', default=0.0)
    is_active = models.BooleanField('是否启用', default=True)
    remark = models.TextField('备注', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'transport_route'
        verbose_name = '运输路径'
        verbose_name_plural = verbose_name
        unique_together = ('source_granary', 'target_granary', 'transport_type')
        ordering = ['source_granary__code']

    def __str__(self):
        return f'{self.source_granary.code}→{self.target_granary.code} ({self.get_transport_type_display()})'

    def clean(self):
        if self.source_granary_id == self.target_granary_id:
            raise ValidationError('起点和终点粮仓不能相同')
        if self.distance_km < 0:
            raise ValidationError({'distance_km': '运输距离不能为负数'})
        if self.estimated_hours < 0:
            raise ValidationError({'estimated_hours': '预计时长不能为负数'})
        if self.cost_per_ton < 0:
            raise ValidationError({'cost_per_ton': '单位运费不能为负数'})


class AllocationBatch(models.Model):
    BATCH_STATUS_CHOICES = (
        ('pending', '待执行'),
        ('loading', '装货中'),
        ('in_transit', '运输中'),
        ('unloading', '卸货中'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
        ('merged', '已合并'),
        ('split', '已拆分'),
    )

    execution = models.ForeignKey('AllocationExecution', on_delete=models.CASCADE,
                                  verbose_name='关联调拨执行', related_name='batches')
    batch_no = models.CharField('批次号', max_length=50, unique=True)
    parent_batch = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True,
                                     verbose_name='父批次', related_name='child_batches')
    status = models.CharField('批次状态', max_length=20, choices=BATCH_STATUS_CHOICES, default='pending')

    quantity = models.FloatField('批次数量(吨)', default=0.0)
    actual_quantity = models.FloatField('实际数量(吨)', blank=True, null=True)
    route = models.ForeignKey(TransportRoute, on_delete=models.SET_NULL, blank=True, null=True,
                              verbose_name='运输路径', related_name='batches')

    estimated_departure = models.DateTimeField('预计出发时间', blank=True, null=True)
    actual_departure = models.DateTimeField('实际出发时间', blank=True, null=True)
    estimated_arrival = models.DateTimeField('预计到达时间', blank=True, null=True)
    actual_arrival = models.DateTimeField('实际到达时间', blank=True, null=True)

    transporter = models.CharField('运输单位', max_length=100, blank=True, null=True)
    vehicle_no = models.CharField('车牌号', max_length=50, blank=True, null=True)
    driver = models.CharField('司机', max_length=50, blank=True, null=True)
    driver_phone = models.CharField('司机电话', max_length=20, blank=True, null=True)

    operator = models.CharField('执行人', max_length=50, blank=True, null=True)
    loss_quantity = models.FloatField('损耗数量(吨)', default=0.0)
    remark = models.TextField('备注', blank=True, null=True)

    completed_at = models.DateTimeField('完成时间', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'allocation_batch'
        verbose_name = '调拨批次'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.batch_no} - {self.get_status_display()}'

    def get_transit_hours(self):
        if self.actual_departure and self.actual_arrival:
            delta = self.actual_arrival - self.actual_departure
            return round(delta.total_seconds() / 3600, 2)
        return None

    def get_loss_rate(self):
        actual = self.actual_quantity or self.quantity
        if actual > 0 and self.loss_quantity > 0:
            return round(self.loss_quantity / actual * 100, 2)
        return 0.0

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({'quantity': '批次数量必须大于0'})
        if self.actual_departure and self.actual_arrival and self.actual_arrival < self.actual_departure:
            raise ValidationError({'actual_arrival': '实际到达时间不能早于出发时间'})
        if self.loss_quantity < 0:
            raise ValidationError({'loss_quantity': '损耗数量不能为负数'})


class ExecutionNode(models.Model):
    NODE_TYPE_CHOICES = (
        ('departure', '出发'),
        ('checkpoint', '途经点'),
        ('transit', '中转仓'),
        ('arrival', '到达'),
        ('custom', '自定义节点'),
    )

    batch = models.ForeignKey(AllocationBatch, on_delete=models.CASCADE,
                              verbose_name='关联批次', related_name='nodes')
    node_type = models.CharField('节点类型', max_length=20, choices=NODE_TYPE_CHOICES)
    node_name = models.CharField('节点名称', max_length=100)
    node_order = models.IntegerField('节点顺序', default=0)

    location = models.CharField('节点位置', max_length=200, blank=True, null=True)
    granary = models.ForeignKey(Granary, on_delete=models.SET_NULL, blank=True, null=True,
                                verbose_name='关联粮仓', related_name='execution_nodes')

    planned_time = models.DateTimeField('计划到达时间', blank=True, null=True)
    actual_time = models.DateTimeField('实际到达时间', blank=True, null=True)
    departed_time = models.DateTimeField('离开时间', blank=True, null=True)

    operator = models.CharField('操作人', max_length=50, blank=True, null=True)
    quantity_checked = models.FloatField('核对数量(吨)', blank=True, null=True)
    temperature = models.FloatField('粮温(℃)', blank=True, null=True)
    humidity = models.FloatField('湿度(%)', blank=True, null=True)
    remark = models.TextField('备注', blank=True, null=True)
    is_completed = models.BooleanField('是否完成', default=False)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'execution_node'
        verbose_name = '执行节点'
        verbose_name_plural = verbose_name
        ordering = ['batch_id', 'node_order', 'created_at']

    def __str__(self):
        return f'{self.batch.batch_no} - {self.node_name}'

    def clean(self):
        if self.planned_time and self.actual_time and self.actual_time < self.planned_time:
            pass
        if self.actual_time and self.departed_time and self.departed_time < self.actual_time:
            raise ValidationError({'departed_time': '离开时间不能早于到达时间'})


class AbnormalLoss(models.Model):
    LOSS_TYPE_CHOICES = (
        ('spillage', '撒漏损耗'),
        ('theft', '偷盗损失'),
        ('moisture', '水分损耗'),
        ('mold', '霉变损耗'),
        ('pest', '虫害损耗'),
        ('damage', '破损损耗'),
        ('other', '其他损耗'),
    )
    SEVERITY_CHOICES = (
        ('minor', '轻微'),
        ('moderate', '一般'),
        ('serious', '严重'),
    )
    STATUS_CHOICES = (
        ('reported', '已上报'),
        ('investigating', '调查中'),
        ('confirmed', '已确认'),
        ('resolved', '已处理'),
        ('closed', '已归档'),
    )

    batch = models.ForeignKey(AllocationBatch, on_delete=models.CASCADE,
                              verbose_name='关联批次', related_name='abnormal_losses')
    node = models.ForeignKey(ExecutionNode, on_delete=models.SET_NULL, blank=True, null=True,
                             verbose_name='发生节点', related_name='losses')
    loss_type = models.CharField('损耗类型', max_length=20, choices=LOSS_TYPE_CHOICES)
    severity = models.CharField('严重程度', max_length=20, choices=SEVERITY_CHOICES, default='moderate')
    status = models.CharField('处理状态', max_length=20, choices=STATUS_CHOICES, default='reported')

    loss_quantity = models.FloatField('损耗数量(吨)', default=0.0)
    estimated_cost = models.FloatField('预估损失金额(元)', default=0.0)
    actual_cost = models.FloatField('实际损失金额(元)', blank=True, null=True)

    discovered_time = models.DateTimeField('发现时间', default=timezone.now)
    discovered_location = models.CharField('发现地点', max_length=200, blank=True, null=True)
    discovered_by = models.CharField('发现人', max_length=50, blank=True, null=True)

    description = models.TextField('损耗描述')
    cause_analysis = models.TextField('原因分析', blank=True, null=True)
    handling_measures = models.TextField('处置措施', blank=True, null=True)

    handled_by = models.CharField('处理人', max_length=50, blank=True, null=True)
    handled_time = models.DateTimeField('处理时间', blank=True, null=True)
    handling_result = models.TextField('处理结果', blank=True, null=True)

    confirmed_by = models.CharField('确认人', max_length=50, blank=True, null=True)
    confirmed_time = models.DateTimeField('确认时间', blank=True, null=True)
    remark = models.TextField('备注', blank=True, null=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'abnormal_loss'
        verbose_name = '异常损耗'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.batch.batch_no} - {self.get_loss_type_display()} {self.loss_quantity}吨'

    def clean(self):
        if self.loss_quantity <= 0:
            raise ValidationError({'loss_quantity': '损耗数量必须大于0'})
        if self.estimated_cost < 0:
            raise ValidationError({'estimated_cost': '预估损失金额不能为负数'})
        if self.actual_cost is not None and self.actual_cost < 0:
            raise ValidationError({'actual_cost': '实际损失金额不能为负数'})


class ArrivalVerification(models.Model):
    VERIFICATION_STATUS_CHOICES = (
        ('pending', '待复核'),
        ('verifying', '复核中'),
        ('passed', '复核通过'),
        ('discrepancy', '存在差异'),
        ('failed', '复核不通过'),
    )

    batch = models.OneToOneField(AllocationBatch, on_delete=models.CASCADE,
                                  verbose_name='关联批次', related_name='arrival_verification')
    verification_no = models.CharField('复核单号', max_length=50, unique=True)
    status = models.CharField('复核状态', max_length=20, choices=VERIFICATION_STATUS_CHOICES, default='pending')

    planned_quantity = models.FloatField('计划数量(吨)', default=0.0)
    actual_loaded = models.FloatField('实际装车数量(吨)', blank=True, null=True)
    actual_received = models.FloatField('实际到仓数量(吨)', blank=True, null=True)
    quantity_diff = models.FloatField('数量差异(吨)', default=0.0)

    arrival_time = models.DateTimeField('到仓时间', blank=True, null=True)
    unloading_start = models.DateTimeField('开始卸货时间', blank=True, null=True)
    unloading_end = models.DateTimeField('卸货完成时间', blank=True, null=True)

    quality_check_passed = models.BooleanField('质检是否合格', default=True)
    quality_report = models.TextField('质检报告', blank=True, null=True)
    moisture_content = models.FloatField('水分含量(%)', blank=True, null=True)
    impurity_rate = models.FloatField('杂质率(%)', blank=True, null=True)
    temperature = models.FloatField('粮温(℃)', blank=True, null=True)

    verifier = models.CharField('复核人', max_length=50, blank=True, null=True)
    verification_time = models.DateTimeField('复核时间', blank=True, null=True)
    discrepancy_description = models.TextField('差异说明', blank=True, null=True)
    handling_suggestion = models.TextField('处理建议', blank=True, null=True)

    confirmed_by = models.CharField('最终确认人', max_length=50, blank=True, null=True)
    confirmed_time = models.DateTimeField('确认时间', blank=True, null=True)
    remark = models.TextField('备注', blank=True, null=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'arrival_verification'
        verbose_name = '到仓复核'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.verification_no} - {self.get_status_display()}'

    def get_diff_rate(self):
        if self.planned_quantity > 0 and self.quantity_diff != 0:
            return round(abs(self.quantity_diff) / self.planned_quantity * 100, 2)
        return 0.0

    def clean(self):
        if self.planned_quantity <= 0:
            raise ValidationError({'planned_quantity': '计划数量必须大于0'})
        if self.arrival_time and self.unloading_start and self.unloading_start < self.arrival_time:
            raise ValidationError({'unloading_start': '开始卸货时间不能早于到仓时间'})
        if self.unloading_start and self.unloading_end and self.unloading_end < self.unloading_start:
            raise ValidationError({'unloading_end': '卸货完成时间不能早于开始时间'})


class AllocationExecution(models.Model):
    STATUS_CHOICES = (
        ('scheduled', '已计划'),
        ('loading', '装货中'),
        ('in_transit', '运输中'),
        ('unloading', '卸货中'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
    )

    suggestion = models.OneToOneField(AllocationSuggestion, on_delete=models.PROTECT,
                                      verbose_name='关联调拨建议', related_name='execution')
    execution_no = models.CharField('调拨单号', max_length=50, unique=True)
    status = models.CharField('执行状态', max_length=20, choices=STATUS_CHOICES, default='scheduled')

    actual_quantity = models.FloatField('实际调拨数量(吨)', blank=True, null=True)
    estimated_departure = models.DateTimeField('预计出发时间', blank=True, null=True)
    actual_departure = models.DateTimeField('实际出发时间', blank=True, null=True)
    estimated_arrival = models.DateTimeField('预计到达时间', blank=True, null=True)
    actual_arrival = models.DateTimeField('实际到达时间', blank=True, null=True)

    route = models.ForeignKey(TransportRoute, on_delete=models.SET_NULL, blank=True, null=True,
                              verbose_name='运输路径', related_name='executions')

    transporter = models.CharField('运输单位', max_length=100, blank=True, null=True)
    vehicle_no = models.CharField('车牌号', max_length=50, blank=True, null=True)
    driver = models.CharField('司机', max_length=50, blank=True, null=True)
    driver_phone = models.CharField('司机电话', max_length=20, blank=True, null=True)

    operator = models.CharField('执行人', max_length=50, blank=True, null=True)
    quality_check_result = models.TextField('质检结果', blank=True, null=True)
    loss_quantity = models.FloatField('损耗数量(吨)', default=0.0)
    remark = models.TextField('备注', blank=True, null=True)

    completed_at = models.DateTimeField('完成时间', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'allocation_execution'
        verbose_name = '调拨执行'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.execution_no} - {self.get_status_display()}'

    def get_transit_hours(self):
        if self.actual_departure and self.actual_arrival:
            delta = self.actual_arrival - self.actual_departure
            return round(delta.total_seconds() / 3600, 2)
        return None

    def get_total_batch_quantity(self):
        return sum(b.quantity for b in self.batches.all())

    def get_completed_batch_count(self):
        return self.batches.filter(status='completed').count()

    def get_total_batch_count(self):
        return self.batches.count()

    def get_completion_rate(self):
        total = self.get_total_batch_count()
        if total > 0:
            return round(self.get_completed_batch_count() / total * 100, 1)
        return 0.0

    def get_total_loss(self):
        return sum(b.loss_quantity for b in self.batches.filter(status='completed'))

    def get_average_transit_hours(self):
        completed = self.batches.filter(status='completed')
        hours = [b.get_transit_hours() for b in completed if b.get_transit_hours()]
        if hours:
            return round(sum(hours) / len(hours), 2)
        return 0.0

    def clean(self):
        if self.actual_departure and self.actual_arrival and self.actual_arrival < self.actual_departure:
            raise ValidationError({'actual_arrival': '实际到达时间不能早于出发时间'})
        if self.loss_quantity < 0:
            raise ValidationError({'loss_quantity': '损耗数量不能为负数'})


class EmergencyEvent(models.Model):
    EVENT_TYPE_CHOICES = (
        ('mold', '突发霉变'),
        ('pest', '虫害暴发'),
        ('transport_disrupt', '运输中断'),
        ('natural_disaster', '自然灾害'),
        ('equipment_failure', '设备故障'),
        ('quality_accident', '质量事故'),
        ('other', '其他突发事件'),
    )
    SEVERITY_CHOICES = (
        ('general', '一般'),
        ('major', '较大'),
        ('severe', '重大'),
        ('extreme', '特别重大'),
    )
    STATUS_CHOICES = (
        ('reported', '已上报'),
        ('analyzing', '分析中'),
        ('responding', '处置中'),
        ('monitoring', '监测中'),
        ('resolved', '已解除'),
        ('closed', '已归档'),
    )

    event_no = models.CharField('事件编号', max_length=50, unique=True)
    event_type = models.CharField('事件类型', max_length=30, choices=EVENT_TYPE_CHOICES)
    severity = models.CharField('严重程度', max_length=20, choices=SEVERITY_CHOICES, default='general')
    status = models.CharField('事件状态', max_length=20, choices=STATUS_CHOICES, default='reported')

    title = models.CharField('事件标题', max_length=200)
    description = models.TextField('事件描述')
    location = models.CharField('发生地点', max_length=200)
    latitude = models.FloatField('纬度', blank=True, null=True)
    longitude = models.FloatField('经度', blank=True, null=True)

    reported_by = models.CharField('上报人', max_length=100)
    reported_time = models.DateTimeField('上报时间', default=timezone.now)
    first_response_time = models.DateTimeField('首次响应时间', blank=True, null=True)

    granary = models.ForeignKey(Granary, on_delete=models.SET_NULL, blank=True, null=True,
                                verbose_name='关联粮仓', related_name='emergency_events')
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, blank=True, null=True,
                               verbose_name='关联区域', related_name='emergency_events')

    affected_area = models.FloatField('影响面积(平方米)', blank=True, null=True)
    affected_quantity = models.FloatField('影响数量(吨)', blank=True, null=True)
    estimated_loss = models.FloatField('预估损失(元)', blank=True, null=True)
    actual_loss = models.FloatField('实际损失(元)', blank=True, null=True)

    is_upgraded = models.BooleanField('是否升级', default=False)
    upgrade_reason = models.TextField('升级原因', blank=True, null=True)
    upgraded_at = models.DateTimeField('升级时间', blank=True, null=True)
    upgraded_by = models.CharField('升级操作人', max_length=100, blank=True, null=True)

    resolved_time = models.DateTimeField('解除时间', blank=True, null=True)
    resolved_by = models.CharField('解除操作人', max_length=100, blank=True, null=True)
    resolution_summary = models.TextField('处置总结', blank=True, null=True)

    closed_time = models.DateTimeField('归档时间', blank=True, null=True)
    closed_by = models.CharField('归档人', max_length=100, blank=True, null=True)
    archive_remark = models.TextField('归档备注', blank=True, null=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'emergency_event'
        verbose_name = '应急事件'
        verbose_name_plural = verbose_name
        ordering = ['-reported_time']

    def __str__(self):
        return f'{self.event_no} - {self.title}'

    def get_response_duration_minutes(self):
        if self.first_response_time and self.reported_time:
            delta = self.first_response_time - self.reported_time
            return round(delta.total_seconds() / 60, 1)
        return None

    def get_resolution_duration_hours(self):
        if self.resolved_time and self.reported_time:
            delta = self.resolved_time - self.reported_time
            return round(delta.total_seconds() / 3600, 1)
        return None


class EmergencyImpact(models.Model):
    IMPACT_TYPE_CHOICES = (
        ('granary', '受影响粮仓'),
        ('batch', '受影响批次'),
        ('route', '受影响路径'),
        ('execution', '受影响在途任务'),
    )

    event = models.ForeignKey(EmergencyEvent, on_delete=models.CASCADE,
                              verbose_name='关联事件', related_name='impacts')
    impact_type = models.CharField('影响类型', max_length=20, choices=IMPACT_TYPE_CHOICES)

    granary = models.ForeignKey(Granary, on_delete=models.CASCADE, blank=True, null=True,
                                verbose_name='受影响粮仓', related_name='emergency_impacts')
    batch = models.ForeignKey(AllocationBatch, on_delete=models.CASCADE, blank=True, null=True,
                              verbose_name='受影响批次', related_name='emergency_impacts')
    route = models.ForeignKey(TransportRoute, on_delete=models.CASCADE, blank=True, null=True,
                              verbose_name='受影响路径', related_name='emergency_impacts')
    execution = models.ForeignKey(AllocationExecution, on_delete=models.CASCADE, blank=True, null=True,
                                  verbose_name='受影响执行单', related_name='emergency_impacts')

    impact_description = models.TextField('影响描述', blank=True, null=True)
    affected_quantity = models.FloatField('影响数量(吨)', blank=True, null=True)
    severity_assessment = models.CharField('影响程度评估', max_length=200, blank=True, null=True)

    is_handled = models.BooleanField('是否已处置', default=False)
    handled_at = models.DateTimeField('处置时间', blank=True, null=True)
    handled_by = models.CharField('处置人', max_length=100, blank=True, null=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'emergency_impact'
        verbose_name = '事件影响'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.event.event_no} - {self.get_impact_type_display()}'

    def clean(self):
        impact_fields = [self.granary, self.batch, self.route, self.execution]
        filled_fields = [f for f in impact_fields if f is not None]
        if len(filled_fields) != 1:
            raise ValidationError('必须且只能指定一种受影响对象')


class EmergencyPlan(models.Model):
    PLAN_STATUS_CHOICES = (
        ('draft', '草稿'),
        ('pending', '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
        ('executing', '执行中'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
    )
    PLAN_TYPE_CHOICES = (
        ('disposal', '应急处置方案'),
        ('reroute', '替代调运方案'),
        ('transfer', '紧急调拨方案'),
        ('comprehensive', '综合处置方案'),
    )

    event = models.ForeignKey(EmergencyEvent, on_delete=models.CASCADE,
                              verbose_name='关联事件', related_name='plans')
    plan_no = models.CharField('方案编号', max_length=50, unique=True)
    plan_type = models.CharField('方案类型', max_length=20, choices=PLAN_TYPE_CHOICES)
    plan_name = models.CharField('方案名称', max_length=200)
    status = models.CharField('方案状态', max_length=20, choices=PLAN_STATUS_CHOICES, default='draft')

    objectives = models.TextField('处置目标')
    measures = models.TextField('处置措施')
    resource_requirements = models.TextField('资源需求', blank=True, null=True)
    expected_effect = models.TextField('预期效果', blank=True, null=True)

    estimated_cost = models.FloatField('预估费用(元)', blank=True, null=True)
    actual_cost = models.FloatField('实际费用(元)', blank=True, null=True)
    estimated_duration_hours = models.FloatField('预估时长(小时)', blank=True, null=True)
    actual_duration_hours = models.FloatField('实际时长(小时)', blank=True, null=True)

    created_by = models.CharField('编制人', max_length=100)
    created_at = models.DateTimeField('编制时间', auto_now_add=True)

    approved_by = models.CharField('审批人', max_length=100, blank=True, null=True)
    approved_at = models.DateTimeField('审批时间', blank=True, null=True)
    approval_opinion = models.TextField('审批意见', blank=True, null=True)

    executed_by = models.CharField('执行人', max_length=100, blank=True, null=True)
    execution_start = models.DateTimeField('执行开始时间', blank=True, null=True)
    execution_end = models.DateTimeField('执行结束时间', blank=True, null=True)
    execution_result = models.TextField('执行结果', blank=True, null=True)

    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'emergency_plan'
        verbose_name = '应急方案'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.plan_no} - {self.plan_name}'


class AlternativeRoute(models.Model):
    STATUS_CHOICES = (
        ('suggested', '建议路线'),
        ('selected', '已选用'),
        ('rejected', '已拒绝'),
        ('completed', '已完成'),
    )

    plan = models.ForeignKey(EmergencyPlan, on_delete=models.CASCADE,
                             verbose_name='关联方案', related_name='alternative_routes')
    original_route = models.ForeignKey(TransportRoute, on_delete=models.SET_NULL, blank=True, null=True,
                                       verbose_name='原运输路径', related_name='emergency_alternatives')
    original_batch = models.ForeignKey(AllocationBatch, on_delete=models.SET_NULL, blank=True, null=True,
                                       verbose_name='原运输批次', related_name='emergency_alternatives')

    alternative_route = models.ForeignKey(TransportRoute, on_delete=models.SET_NULL, blank=True, null=True,
                                          verbose_name='替代运输路径', related_name='as_emergency_alternative')
    route_description = models.TextField('路线描述')
    waypoints = models.TextField('途经点', blank=True, null=True)

    distance_km = models.FloatField('运输距离(公里)', default=0.0)
    estimated_hours = models.FloatField('预计时长(小时)', default=0.0)
    cost_per_ton = models.FloatField('单位运费(元/吨)', default=0.0)
    total_cost = models.FloatField('总运费(元)', blank=True, null=True)

    transport_type = models.CharField('运输方式', max_length=20,
                                      choices=TransportRoute.TRANSPORT_TYPE_CHOICES, default='road')
    priority_score = models.FloatField('优先级评分', default=0.0)
    risk_assessment = models.TextField('风险评估', blank=True, null=True)

    source_granary = models.ForeignKey(Granary, on_delete=models.CASCADE, blank=True, null=True,
                                       related_name='alt_route_sources', verbose_name='出发粮仓')
    target_granary = models.ForeignKey(Granary, on_delete=models.CASCADE, blank=True, null=True,
                                       related_name='alt_route_targets', verbose_name='目的粮仓')

    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='suggested')
    selected_by = models.CharField('选用人', max_length=100, blank=True, null=True)
    selected_at = models.DateTimeField('选用时间', blank=True, null=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'alternative_route'
        verbose_name = '替代路线'
        verbose_name_plural = verbose_name
        ordering = ['priority_score', '-created_at']

    def __str__(self):
        return f'{self.plan.plan_no} - {self.route_description[:50]}'


class EmergencyCommand(models.Model):
    COMMAND_TYPE_CHOICES = (
        ('dispatch', '调度指令'),
        ('assignment', '任务分派'),
        ('coordination', '协调指令'),
        ('notice', '通知公告'),
    )
    PRIORITY_CHOICES = (
        ('urgent', '紧急'),
        ('high', '高'),
        ('normal', '普通'),
        ('low', '低'),
    )
    STATUS_CHOICES = (
        ('pending', '待执行'),
        ('executing', '执行中'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
    )

    event = models.ForeignKey(EmergencyEvent, on_delete=models.CASCADE,
                              verbose_name='关联事件', related_name='commands')
    command_no = models.CharField('指令编号', max_length=50, unique=True)
    command_type = models.CharField('指令类型', max_length=20, choices=COMMAND_TYPE_CHOICES)
    priority = models.CharField('优先级', max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')

    title = models.CharField('指令标题', max_length=200)
    content = models.TextField('指令内容')
    requirements = models.TextField('执行要求', blank=True, null=True)

    issuer = models.CharField('签发人', max_length=100)
    issued_at = models.DateTimeField('签发时间', default=timezone.now)

    assignee = models.CharField('责任人', max_length=100)
    assignee_department = models.CharField('责任部门', max_length=100, blank=True, null=True)
    deadline = models.DateTimeField('要求完成时间', blank=True, null=True)

    actual_start = models.DateTimeField('实际开始时间', blank=True, null=True)
    actual_end = models.DateTimeField('实际完成时间', blank=True, null=True)
    execution_result = models.TextField('执行结果', blank=True, null=True)
    feedback_attachments = models.TextField('反馈附件', blank=True, null=True)

    acknowledged_by = models.CharField('签收人', max_length=100, blank=True, null=True)
    acknowledged_at = models.DateTimeField('签收时间', blank=True, null=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'emergency_command'
        verbose_name = '指挥调度'
        verbose_name_plural = verbose_name
        ordering = ['-issued_at']

    def __str__(self):
        return f'{self.command_no} - {self.title}'

    def get_remaining_hours(self):
        if self.status == 'completed' or not self.deadline:
            return 0
        now = timezone.now()
        if now >= self.deadline:
            return 0
        delta = self.deadline - now
        return round(delta.total_seconds() / 3600, 1)

    def is_overdue(self):
        if self.status == 'completed' or not self.deadline:
            return False
        if self.actual_end:
            return self.actual_end > self.deadline
        return timezone.now() > self.deadline


class EmergencyFeedback(models.Model):
    FEEDBACK_TYPE_CHOICES = (
        ('progress', '进度汇报'),
        ('situation', '现场情况'),
        ('problem', '问题上报'),
        ('result', '处置结果'),
        ('other', '其他反馈'),
    )
    SEVERITY_CHOICES = (
        ('improved', '好转'),
        ('stable', '稳定'),
        ('worsened', '恶化'),
        ('unknown', '未知'),
    )

    event = models.ForeignKey(EmergencyEvent, on_delete=models.CASCADE,
                              verbose_name='关联事件', related_name='feedbacks')
    command = models.ForeignKey(EmergencyCommand, on_delete=models.SET_NULL, blank=True, null=True,
                                verbose_name='关联指令', related_name='feedbacks')
    feedback_type = models.CharField('反馈类型', max_length=20, choices=FEEDBACK_TYPE_CHOICES)
    situation_assessment = models.CharField('现场态势评估', max_length=20,
                                            choices=SEVERITY_CHOICES, default='unknown')

    location = models.CharField('反馈地点', max_length=200, blank=True, null=True)
    reporter = models.CharField('反馈人', max_length=100)
    reporter_phone = models.CharField('联系电话', max_length=20, blank=True, null=True)
    report_time = models.DateTimeField('反馈时间', default=timezone.now)

    content = models.TextField('反馈内容')
    measures_taken = models.TextField('已采取措施', blank=True, null=True)
    needs_assistance = models.BooleanField('需要支援', default=False)
    assistance_details = models.TextField('支援需求', blank=True, null=True)

    temperature = models.FloatField('现场温度(℃)', blank=True, null=True)
    humidity = models.FloatField('现场湿度(%)', blank=True, null=True)
    pest_density = models.FloatField('虫害密度(头/公斤)', blank=True, null=True)
    affected_area = models.FloatField('影响面积(平方米)', blank=True, null=True)

    attachments = models.TextField('附件说明', blank=True, null=True)
    photos = models.TextField('现场照片', blank=True, null=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'emergency_feedback'
        verbose_name = '现场反馈'
        verbose_name_plural = verbose_name
        ordering = ['-report_time']

    def __str__(self):
        return f'{self.event.event_no} - {self.get_feedback_type_display()}'


class EmergencyTask(models.Model):
    TASK_TYPE_CHOICES = (
        ('disposal', '现场处置'),
        ('transport', '运输保障'),
        ('supply', '物资供应'),
        ('monitoring', '监测监控'),
        ('coordination', '协调沟通'),
        ('assessment', '损失评估'),
        ('documentation', '资料归档'),
    )
    STATUS_CHOICES = (
        ('assigned', '已分派'),
        ('accepted', '已接受'),
        ('in_progress', '进行中'),
        ('completed', '已完成'),
        ('delayed', '已延期'),
        ('cancelled', '已取消'),
    )
    PRIORITY_CHOICES = (
        ('critical', '极重要'),
        ('high', '重要'),
        ('medium', '一般'),
        ('low', '次要'),
    )

    event = models.ForeignKey(EmergencyEvent, on_delete=models.CASCADE,
                              verbose_name='关联事件', related_name='tasks')
    command = models.ForeignKey(EmergencyCommand, on_delete=models.SET_NULL, blank=True, null=True,
                                verbose_name='关联指令', related_name='tasks')
    plan = models.ForeignKey(EmergencyPlan, on_delete=models.SET_NULL, blank=True, null=True,
                             verbose_name='关联方案', related_name='tasks')

    task_no = models.CharField('任务编号', max_length=50, unique=True)
    task_type = models.CharField('任务类型', max_length=20, choices=TASK_TYPE_CHOICES)
    title = models.CharField('任务标题', max_length=200)
    description = models.TextField('任务描述')
    priority = models.CharField('优先级', max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='assigned')

    assignee = models.CharField('负责人', max_length=100)
    assignee_department = models.CharField('负责部门', max_length=100, blank=True, null=True)
    assigner = models.CharField('分派人', max_length=100)
    assigned_at = models.DateTimeField('分派时间', default=timezone.now)

    start_time = models.DateTimeField('计划开始时间', blank=True, null=True)
    due_time = models.DateTimeField('截止时间', blank=True, null=True)
    actual_start = models.DateTimeField('实际开始时间', blank=True, null=True)
    actual_end = models.DateTimeField('实际完成时间', blank=True, null=True)

    progress = models.IntegerField('进度(%)', default=0)
    expected_result = models.TextField('预期成果', blank=True, null=True)
    actual_result = models.TextField('实际成果', blank=True, null=True)
    difficulties = models.TextField('遇到的困难', blank=True, null=True)

    accepted_by = models.CharField('接受人', max_length=100, blank=True, null=True)
    accepted_at = models.DateTimeField('接受时间', blank=True, null=True)

    completed_by = models.CharField('完成确认人', max_length=100, blank=True, null=True)
    completed_at = models.DateTimeField('完成确认时间', blank=True, null=True)
    completion_remark = models.TextField('完成备注', blank=True, null=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'emergency_task'
        verbose_name = '应急任务'
        verbose_name_plural = verbose_name
        ordering = ['-assigned_at']

    def __str__(self):
        return f'{self.task_no} - {self.title}'

    def clean(self):
        if self.progress is not None and (self.progress < 0 or self.progress > 100):
            raise ValidationError({'progress': '进度必须在0-100之间'})

    def get_remaining_hours(self):
        if self.status == 'completed' or not self.due_time:
            return 0
        now = timezone.now()
        if now >= self.due_time:
            return 0
        delta = self.due_time - now
        return round(delta.total_seconds() / 3600, 1)

    def is_overdue(self):
        if self.status == 'completed' or not self.due_time:
            return False
        if self.actual_end:
            return self.actual_end > self.due_time
        return timezone.now() > self.due_time


class EmergencyUpgrade(models.Model):
    event = models.ForeignKey(EmergencyEvent, on_delete=models.CASCADE,
                              verbose_name='关联事件', related_name='upgrades')
    original_severity = models.CharField('原严重程度', max_length=20,
                                         choices=EmergencyEvent.SEVERITY_CHOICES)
    new_severity = models.CharField('新严重程度', max_length=20,
                                    choices=EmergencyEvent.SEVERITY_CHOICES)

    reason = models.TextField('升级原因')
    basis = models.TextField('升级依据')
    additional_measures = models.TextField('补充处置措施', blank=True, null=True)

    requested_by = models.CharField('申请人', max_length=100)
    requested_at = models.DateTimeField('申请时间', default=timezone.now)
    approved_by = models.CharField('审批人', max_length=100, blank=True, null=True)
    approved_at = models.DateTimeField('审批时间', blank=True, null=True)
    approval_opinion = models.TextField('审批意见', blank=True, null=True)

    is_approved = models.BooleanField('是否批准', default=False)
    notified_persons = models.TextField('已通知人员', blank=True, null=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'emergency_upgrade'
        verbose_name = '事件升级'
        verbose_name_plural = verbose_name
        ordering = ['-requested_at']

    def __str__(self):
        return f'{self.event.event_no} - 升级'


class EmergencyClosure(models.Model):
    event = models.ForeignKey(EmergencyEvent, on_delete=models.CASCADE,
                              verbose_name='关联事件', related_name='closures')

    verification_results = models.TextField('现场核查结果')
    stability_assessment = models.TextField('稳定性评估')
    remaining_risks = models.TextField('遗留风险', blank=True, null=True)
    followup_actions = models.TextField('后续行动建议', blank=True, null=True)

    total_response_duration = models.FloatField('总响应时长(小时)', blank=True, null=True)
    total_disposal_duration = models.FloatField('总处置时长(小时)', blank=True, null=True)
    resource_usage_summary = models.TextField('资源使用情况', blank=True, null=True)
    lessons_learned = models.TextField('经验教训', blank=True, null=True)
    improvement_suggestions = models.TextField('改进建议', blank=True, null=True)

    requested_by = models.CharField('申请人', max_length=100)
    requested_at = models.DateTimeField('申请时间', default=timezone.now)
    verified_by = models.CharField('核查人', max_length=100, blank=True, null=True)
    verified_at = models.DateTimeField('核查时间', blank=True, null=True)
    approved_by = models.CharField('批准人', max_length=100, blank=True, null=True)
    approved_at = models.DateTimeField('批准时间', blank=True, null=True)

    is_approved = models.BooleanField('是否批准解除', default=False)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'emergency_closure'
        verbose_name = '事件解除'
        verbose_name_plural = verbose_name
        ordering = ['-requested_at']

    def __str__(self):
        return f'{self.event.event_no} - 解除'
