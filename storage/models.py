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
    capacity = models.FloatField('设计容量(吨)', default=0.0)
    current_stock = models.FloatField('当前库存(吨)', default=0.0)
    grain_type = models.ForeignKey(GrainType, on_delete=models.PROTECT,
                                   verbose_name='储粮种类', related_name='granaries')
    location = models.CharField('位置', max_length=200, blank=True, null=True)
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
