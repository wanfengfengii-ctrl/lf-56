from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from .models import (
    GrainType, Granary, TemperatureHumidityLog,
    VentilationLog, PestInspection, RiskAssessment,
    Warning, DisposalTask, DisposalProgressLog,
    InventoryChangeLog, AllocationConfig, AllocationSuggestion,
    AllocationExecution, GrainSituationPrediction,
    Region, TransportRoute, AllocationBatch, ExecutionNode,
    AbnormalLoss, ArrivalVerification,
    EmergencyEvent, EmergencyPlan, EmergencyCommand,
    EmergencyFeedback, EmergencyTask, EmergencyUpgrade,
    EmergencyClosure, AlternativeRoute, EmergencyImpact
)


class GrainTypeForm(forms.ModelForm):
    class Meta:
        model = GrainType
        fields = ['name', 'safe_temp_min', 'safe_temp_max', 'safe_humidity_min',
                  'safe_humidity_max', 'mold_sensitivity', 'pest_sensitivity', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'safe_temp_min': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'safe_temp_max': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'safe_humidity_min': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'safe_humidity_max': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'mold_sensitivity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0.1'}),
            'pest_sensitivity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0.1'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        temp_min = cleaned_data.get('safe_temp_min')
        temp_max = cleaned_data.get('safe_temp_max')
        hum_min = cleaned_data.get('safe_humidity_min')
        hum_max = cleaned_data.get('safe_humidity_max')

        if temp_min is not None and temp_max is not None and temp_min >= temp_max:
            raise ValidationError({'safe_temp_min': '安全温度下限必须小于上限'})
        if hum_min is not None and hum_max is not None and hum_min >= hum_max:
            raise ValidationError({'safe_humidity_min': '安全湿度下限必须小于上限'})
        return cleaned_data


class GranaryForm(forms.ModelForm):
    class Meta:
        model = Granary
        fields = ['code', 'name', 'capacity', 'current_stock', 'grain_type',
                  'location', 'ventilation_status', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'current_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'grain_type': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'ventilation_status': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_code(self):
        code = self.cleaned_data.get('code')
        qs = Granary.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('粮仓编号不能重复，请使用其他编号')
        return code

    def clean(self):
        cleaned_data = super().clean()
        capacity = cleaned_data.get('capacity')
        current_stock = cleaned_data.get('current_stock')
        if capacity is not None and current_stock is not None and current_stock > capacity:
            raise ValidationError({'current_stock': '当前库存不能超过设计容量'})
        return cleaned_data


class TemperatureHumidityLogForm(forms.ModelForm):
    class Meta:
        model = TemperatureHumidityLog
        fields = ['granary', 'record_date', 'temperature', 'humidity', 'recorder', 'remark']
        widgets = {
            'granary': forms.Select(attrs={'class': 'form-select'}),
            'record_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'temperature': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'humidity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'recorder': forms.TextInput(attrs={'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_temperature(self):
        temp = self.cleaned_data.get('temperature')
        if temp is not None and (temp < -40 or temp > 60):
            raise ValidationError('温度值超出合理范围(-40℃ ~ 60℃)')
        return temp

    def clean_humidity(self):
        hum = self.cleaned_data.get('humidity')
        if hum is not None and (hum < 0 or hum > 100):
            raise ValidationError('湿度值超出合理范围(0% ~ 100%)')
        return hum

    def clean(self):
        cleaned_data = super().clean()
        granary = cleaned_data.get('granary')
        record_date = cleaned_data.get('record_date')
        if granary and record_date:
            qs = TemperatureHumidityLog.objects.filter(granary=granary, record_date=record_date)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError('该粮仓当日已有温湿度记录')
        return cleaned_data


class VentilationLogForm(forms.ModelForm):
    class Meta:
        model = VentilationLog
        fields = ['granary', 'start_time', 'end_time', 'ventilation_type',
                  'operator', 'before_temp', 'before_humidity', 'after_temp',
                  'after_humidity', 'remark']
        widgets = {
            'granary': forms.Select(attrs={'class': 'form-select'}),
            'start_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'ventilation_type': forms.Select(attrs={'class': 'form-select'}),
            'operator': forms.TextInput(attrs={'class': 'form-control'}),
            'before_temp': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'before_humidity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'after_temp': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'after_humidity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_time')
        end = cleaned_data.get('end_time')
        if start and end and end < start:
            raise ValidationError({'end_time': '结束时间不能早于开始时间'})
        return cleaned_data


class PestInspectionForm(forms.ModelForm):
    class Meta:
        model = PestInspection
        fields = ['granary', 'inspect_date', 'pest_density', 'pest_type',
                  'sample_points', 'inspector', 'remark']
        widgets = {
            'granary': forms.Select(attrs={'class': 'form-select'}),
            'inspect_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'pest_density': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0'}),
            'pest_type': forms.TextInput(attrs={'class': 'form-control'}),
            'sample_points': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'inspector': forms.TextInput(attrs={'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_pest_density(self):
        density = self.cleaned_data.get('pest_density')
        if density is not None and density < 0:
            raise ValidationError('虫害密度不能为负数')
        return density

    def clean_sample_points(self):
        points = self.cleaned_data.get('sample_points')
        if points is not None and points < 1:
            raise ValidationError('取样点数至少为1')
        return points


class RiskProcessForm(forms.ModelForm):
    class Meta:
        model = RiskAssessment
        fields = ['status', 'disposal_suggestion', 'disposal_person', 'disposal_date']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'disposal_suggestion': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'disposal_person': forms.TextInput(attrs={'class': 'form-control'}),
            'disposal_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.risk_level == 'high':
            self.fields['disposal_suggestion'].required = True

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        suggestion = cleaned_data.get('disposal_suggestion')
        if status == 'processed' and self.instance.risk_level == 'high' and not suggestion:
            raise ValidationError({'disposal_suggestion': '高风险粮仓必须填写处置建议才能标记为已处理'})
        return cleaned_data


class WarningCreateForm(forms.ModelForm):
    class Meta:
        model = Warning
        fields = ['granary', 'warning_level', 'notify_method', 'warning_content', 'notified_person']
        widgets = {
            'granary': forms.Select(attrs={'class': 'form-select'}),
            'warning_level': forms.Select(attrs={'class': 'form-select'}),
            'notify_method': forms.Select(attrs={'class': 'form-select'}),
            'warning_content': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'notified_person': forms.TextInput(attrs={'class': 'form-control'}),
        }


class DisposalTaskAssignForm(forms.ModelForm):
    class Meta:
        model = DisposalTask
        fields = ['task_title', 'task_description', 'assignee', 'assigner', 'deadline', 'priority']
        widgets = {
            'task_title': forms.TextInput(attrs={'class': 'form-control'}),
            'task_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'assignee': forms.TextInput(attrs={'class': 'form-control'}),
            'assigner': forms.TextInput(attrs={'class': 'form-control'}),
            'deadline': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, warning=None, **kwargs):
        super().__init__(*args, **kwargs)
        if warning and not self.initial.get('deadline'):
            hours = warning.get_deadline_hours()
            default_deadline = warning.warning_time + timedelta(hours=hours)
            self.initial['deadline'] = default_deadline.strftime('%Y-%m-%dT%H:%M')
        if warning and not self.initial.get('priority'):
            if warning.warning_level == 'level1':
                self.initial['priority'] = 'urgent'
            elif warning.warning_level == 'level2':
                self.initial['priority'] = 'high'
            else:
                self.initial['priority'] = 'normal'

    def clean_deadline(self):
        deadline = self.cleaned_data.get('deadline')
        if deadline and deadline < timezone.now():
            raise ValidationError('要求完成时间不能早于当前时间')
        return deadline


class DisposalProgressForm(forms.ModelForm):
    class Meta:
        model = DisposalProgressLog
        fields = ['progress_percent', 'progress_description', 'operator', 'remark']
        widgets = {
            'progress_percent': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100'}),
            'progress_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'operator': forms.TextInput(attrs={'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_progress_percent(self):
        progress = self.cleaned_data.get('progress_percent')
        if progress is not None and (progress < 0 or progress > 100):
            raise ValidationError('进度必须在0-100之间')
        return progress


class DisposalSubmitForm(forms.Form):
    disposal_measures = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        label='处置措施'
    )
    disposal_result = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        label='处置结果'
    )
    disposal_attachment = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
        label='附件说明'
    )
    operator = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='提交人'
    )


class DisposalReviewForm(forms.Form):
    reviewer = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='复查人'
    )
    passed = forms.ChoiceField(
        choices=[(True, '复查通过'), (False, '复查不通过')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='复查结论'
    )
    opinion = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=False,
        label='复查意见'
    )


class DisposalArchiveForm(forms.Form):
    archived_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='归档人'
    )
    remark = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
        label='归档备注'
    )


class WarningFilterForm(forms.Form):
    level = forms.ChoiceField(
        choices=[('', '全部等级')] + list(Warning.LEVEL_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    status = forms.ChoiceField(
        choices=[('', '全部状态')] + list(Warning.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    granary = forms.ModelChoiceField(
        queryset=Granary.objects.filter(is_active=True),
        required=False,
        empty_label='全部粮仓',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )


class InventoryChangeLogForm(forms.ModelForm):
    class Meta:
        model = InventoryChangeLog
        fields = ['granary', 'change_date', 'change_type', 'quantity', 'balance_after',
                  'grain_type', 'operator', 'remark']
        widgets = {
            'granary': forms.Select(attrs={'class': 'form-select'}),
            'change_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'change_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'balance_after': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'grain_type': forms.Select(attrs={'class': 'form-select'}),
            'operator': forms.TextInput(attrs={'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity == 0:
            raise ValidationError('变动数量不能为0')
        return quantity

    def clean_balance_after(self):
        balance = self.cleaned_data.get('balance_after')
        if balance is not None and balance < 0:
            raise ValidationError('变动后库存不能为负数')
        return balance


class AllocationConfigForm(forms.ModelForm):
    class Meta:
        model = AllocationConfig
        fields = ['name', 'description', 'is_default', 'safety_stock_ratio',
                  'min_transfer_quantity', 'max_transfer_quantity', 'priority_rule',
                  'risk_weight', 'inventory_weight', 'distance_weight',
                  'high_risk_threshold', 'low_inventory_threshold',
                  'high_inventory_threshold', 'allow_cross_grain_type',
                  'auto_approve_below']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'safety_stock_ratio': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '100'}),
            'min_transfer_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'max_transfer_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'priority_rule': forms.Select(attrs={'class': 'form-select'}),
            'risk_weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '1'}),
            'inventory_weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '1'}),
            'distance_weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '1'}),
            'high_risk_threshold': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '100'}),
            'low_inventory_threshold': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '100'}),
            'high_inventory_threshold': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '100'}),
            'allow_cross_grain_type': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_approve_below': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        total_weight = (cleaned_data.get('risk_weight') or 0) + \
                       (cleaned_data.get('inventory_weight') or 0) + \
                       (cleaned_data.get('distance_weight') or 0)
        if abs(total_weight - 1.0) > 0.01:
            raise ValidationError('风险、库存、距离权重之和必须等于1')
        low_inv = cleaned_data.get('low_inventory_threshold')
        high_inv = cleaned_data.get('high_inventory_threshold')
        if low_inv is not None and high_inv is not None and low_inv >= high_inv:
            raise ValidationError({'low_inventory_threshold': '低库存阈值必须小于高库存阈值'})
        min_qty = cleaned_data.get('min_transfer_quantity')
        max_qty = cleaned_data.get('max_transfer_quantity')
        if min_qty is not None and max_qty is not None and min_qty >= max_qty:
            raise ValidationError({'min_transfer_quantity': '最小调拨数量必须小于最大调拨数量'})
        return cleaned_data


class AllocationSuggestionForm(forms.ModelForm):
    class Meta:
        model = AllocationSuggestion
        fields = ['source_granary', 'target_granary', 'grain_type',
                  'suggested_quantity', 'priority_level', 'reason', 'expected_benefit']
        widgets = {
            'source_granary': forms.Select(attrs={'class': 'form-select'}),
            'target_granary': forms.Select(attrs={'class': 'form-select'}),
            'grain_type': forms.Select(attrs={'class': 'form-select'}),
            'suggested_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'priority_level': forms.Select(attrs={'class': 'form-select'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'expected_benefit': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        source = cleaned_data.get('source_granary')
        target = cleaned_data.get('target_granary')
        if source and target and source.id == target.id:
            raise ValidationError({'target_granary': '目标粮仓不能与源粮仓相同'})
        qty = cleaned_data.get('suggested_quantity')
        if qty is not None and qty <= 0:
            raise ValidationError({'suggested_quantity': '调拨数量必须大于0'})
        return cleaned_data


class AllocationSuggestionApproveForm(forms.Form):
    approved_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='审批人'
    )
    approval_opinion = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
        label='审批意见'
    )


class AllocationExecutionForm(forms.ModelForm):
    class Meta:
        model = AllocationExecution
        fields = ['status', 'actual_quantity', 'estimated_departure', 'actual_departure',
                  'estimated_arrival', 'actual_arrival', 'transporter', 'vehicle_no',
                  'driver', 'driver_phone', 'operator', 'quality_check_result',
                  'loss_quantity', 'remark']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'actual_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'estimated_departure': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'actual_departure': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'estimated_arrival': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'actual_arrival': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'transporter': forms.TextInput(attrs={'class': 'form-control'}),
            'vehicle_no': forms.TextInput(attrs={'class': 'form-control'}),
            'driver': forms.TextInput(attrs={'class': 'form-control'}),
            'driver_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'operator': forms.TextInput(attrs={'class': 'form-control'}),
            'quality_check_result': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'loss_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        actual_dep = cleaned_data.get('actual_departure')
        actual_arr = cleaned_data.get('actual_arrival')
        if actual_dep and actual_arr and actual_arr < actual_dep:
            raise ValidationError({'actual_arrival': '实际到达时间不能早于出发时间'})
        loss = cleaned_data.get('loss_quantity')
        if loss is not None and loss < 0:
            raise ValidationError({'loss_quantity': '损耗数量不能为负数'})
        return cleaned_data


class PredictionGenerateForm(forms.Form):
    horizon_days = forms.ChoiceField(
        choices=GrainSituationPrediction.PREDICTION_HORIZON_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label='预测周期'
    )
    granary = forms.ModelChoiceField(
        queryset=Granary.objects.filter(is_active=True),
        required=False,
        empty_label='全部粮仓',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )


class AllocationGenerateForm(forms.Form):
    config = forms.ModelChoiceField(
        queryset=AllocationConfig.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label='使用配置'
    )
    grain_type = forms.ModelChoiceField(
        queryset=GrainType.objects.all(),
        required=False,
        empty_label='全部品类',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label='粮食品类'
    )


class RegionForm(forms.ModelForm):
    class Meta:
        model = Region
        fields = ['code', 'name', 'parent', 'description']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = Region.objects.exclude(pk=self.instance.pk) if self.instance.pk else Region.objects.all()
        self.fields['parent'].required = False
        self.fields['parent'].empty_label = '无（顶级区域）'


class TransportRouteForm(forms.ModelForm):
    class Meta:
        model = TransportRoute
        fields = ['source_granary', 'target_granary', 'transport_type', 'distance_km',
                  'estimated_hours', 'cost_per_ton', 'is_active', 'remark']
        widgets = {
            'source_granary': forms.Select(attrs={'class': 'form-select'}),
            'target_granary': forms.Select(attrs={'class': 'form-select'}),
            'transport_type': forms.Select(attrs={'class': 'form-select'}),
            'distance_km': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0'}),
            'estimated_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0'}),
            'cost_per_ton': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['source_granary'].queryset = Granary.objects.filter(is_active=True)
        self.fields['target_granary'].queryset = Granary.objects.filter(is_active=True)

    def clean(self):
        cleaned_data = super().clean()
        source = cleaned_data.get('source_granary')
        target = cleaned_data.get('target_granary')
        if source and target and source.id == target.id:
            raise ValidationError({'target_granary': '目标粮仓不能与源粮仓相同'})
        return cleaned_data


class AllocationBatchForm(forms.ModelForm):
    class Meta:
        model = AllocationBatch
        fields = ['quantity', 'route', 'estimated_departure', 'estimated_arrival',
                  'transporter', 'vehicle_no', 'driver', 'driver_phone', 'remark']
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'route': forms.Select(attrs={'class': 'form-select'}),
            'estimated_departure': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'estimated_arrival': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'transporter': forms.TextInput(attrs={'class': 'form-control'}),
            'vehicle_no': forms.TextInput(attrs={'class': 'form-control'}),
            'driver': forms.TextInput(attrs={'class': 'form-control'}),
            'driver_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.execution = kwargs.pop('execution', None)
        super().__init__(*args, **kwargs)
        self.fields['route'].required = False
        self.fields['route'].queryset = TransportRoute.objects.filter(is_active=True)
        self.fields['route'].empty_label = '请选择运输路径'

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty <= 0:
            raise ValidationError('批次数量必须大于0')
        return qty


class BatchSplitForm(forms.Form):
    quantities = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                     'placeholder': '请输入各批次数量，用逗号分隔，例如：50,30,20'}),
        label='拆分数量'
    )
    operator = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
        label='操作人'
    )

    def clean_quantities(self):
        text = self.cleaned_data.get('quantities', '')
        parts = [p.strip() for p in text.replace('，', ',').split(',') if p.strip()]
        try:
            quantities = [float(p) for p in parts]
        except ValueError:
            raise ValidationError('请输入有效的数字，用逗号分隔')
        if len(quantities) < 2:
            raise ValidationError('至少拆分为2个批次')
        if any(q <= 0 for q in quantities):
            raise ValidationError('每个批次数量必须大于0')
        return quantities


class BatchMergeForm(forms.Form):
    batch_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    operator = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
        label='操作人'
    )


class ExecutionNodeForm(forms.ModelForm):
    class Meta:
        model = ExecutionNode
        fields = ['node_type', 'node_name', 'node_order', 'location', 'granary',
                  'planned_time', 'remark']
        widgets = {
            'node_type': forms.Select(attrs={'class': 'form-select'}),
            'node_name': forms.TextInput(attrs={'class': 'form-control'}),
            'node_order': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'granary': forms.Select(attrs={'class': 'form-select'}),
            'planned_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['granary'].required = False
        self.fields['granary'].queryset = Granary.objects.filter(is_active=True)
        self.fields['granary'].empty_label = '无'
        self.fields['location'].required = False


class NodeCompleteForm(forms.Form):
    operator = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
        label='操作人'
    )
    quantity_checked = forms.FloatField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        required=False,
        label='核对数量(吨)'
    )
    temperature = forms.FloatField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
        required=False,
        label='粮温(℃)'
    )
    humidity = forms.FloatField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '100'}),
        required=False,
        label='湿度(%)'
    )
    remark = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
        label='备注'
    )


class AbnormalLossForm(forms.ModelForm):
    class Meta:
        model = AbnormalLoss
        fields = ['loss_type', 'severity', 'loss_quantity', 'estimated_cost',
                  'discovered_location', 'discovered_by', 'description']
        widgets = {
            'loss_type': forms.Select(attrs={'class': 'form-select'}),
            'severity': forms.Select(attrs={'class': 'form-select'}),
            'loss_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'estimated_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'discovered_location': forms.TextInput(attrs={'class': 'form-control'}),
            'discovered_by': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['discovered_location'].required = False
        self.fields['discovered_by'].required = False
        self.fields['estimated_cost'].required = False

    def clean_loss_quantity(self):
        qty = self.cleaned_data.get('loss_quantity')
        if qty is not None and qty <= 0:
            raise ValidationError('损耗数量必须大于0')
        return qty


class LossHandleForm(forms.Form):
    cause_analysis = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=False,
        label='原因分析'
    )
    handling_measures = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=False,
        label='处置措施'
    )
    handling_result = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=False,
        label='处理结果'
    )
    actual_cost = forms.FloatField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        required=False,
        label='实际损失金额(元)'
    )
    handled_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
        label='处理人'
    )
    confirmed_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
        label='确认人'
    )
    remark = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
        label='备注'
    )


class ArrivalVerificationForm(forms.ModelForm):
    class Meta:
        model = ArrivalVerification
        fields = ['actual_received', 'quality_check_passed', 'quality_report',
                  'moisture_content', 'impurity_rate', 'temperature',
                  'verifier', 'discrepancy_description', 'handling_suggestion', 'remark']
        widgets = {
            'actual_received': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'quality_check_passed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'quality_report': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'moisture_content': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '100'}),
            'impurity_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '100'}),
            'temperature': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'verifier': forms.TextInput(attrs={'class': 'form-control'}),
            'discrepancy_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'handling_suggestion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['actual_received'].required = False
        self.fields['quality_report'].required = False
        self.fields['moisture_content'].required = False
        self.fields['impurity_rate'].required = False
        self.fields['temperature'].required = False
        self.fields['verifier'].required = False
        self.fields['discrepancy_description'].required = False
        self.fields['handling_suggestion'].required = False
        self.fields['remark'].required = False

    def clean_actual_received(self):
        qty = self.cleaned_data.get('actual_received')
        if qty is not None and qty < 0:
            raise ValidationError('实际到仓数量不能为负数')
        return qty


class VerificationConfirmForm(forms.Form):
    confirmed_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='最终确认人'
    )
    handling_suggestion = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=False,
        label='处理建议'
    )


class GranaryRegionForm(forms.ModelForm):
    class Meta:
        model = Granary
        fields = ['code', 'name', 'region', 'capacity', 'current_stock', 'grain_type',
                  'location', 'latitude', 'longitude', 'ventilation_status', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'region': forms.Select(attrs={'class': 'form-select'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'current_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'grain_type': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'ventilation_status': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['region'].required = False
        self.fields['region'].queryset = Region.objects.all()
        self.fields['region'].empty_label = '未指定区域'
        self.fields['latitude'].required = False
        self.fields['longitude'].required = False
        self.fields['location'].required = False


class EmergencyEventForm(forms.ModelForm):
    class Meta:
        model = EmergencyEvent
        fields = ['event_type', 'severity', 'title', 'description', 'location',
                  'latitude', 'longitude', 'reported_by', 'granary', 'region',
                  'affected_area', 'affected_quantity', 'estimated_loss']
        widgets = {
            'event_type': forms.Select(attrs={'class': 'form-select'}),
            'severity': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'reported_by': forms.TextInput(attrs={'class': 'form-control'}),
            'granary': forms.Select(attrs={'class': 'form-select'}),
            'region': forms.Select(attrs={'class': 'form-select'}),
            'affected_area': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'affected_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'estimated_loss': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['granary'].required = False
        self.fields['granary'].queryset = Granary.objects.filter(is_active=True)
        self.fields['granary'].empty_label = '无'
        self.fields['region'].required = False
        self.fields['region'].queryset = Region.objects.all()
        self.fields['region'].empty_label = '无'
        self.fields['latitude'].required = False
        self.fields['longitude'].required = False
        self.fields['affected_area'].required = False
        self.fields['affected_quantity'].required = False
        self.fields['estimated_loss'].required = False


class EmergencyEventFilterForm(forms.Form):
    event_type = forms.ChoiceField(
        choices=[('', '全部类型')] + list(EmergencyEvent.EVENT_TYPE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    severity = forms.ChoiceField(
        choices=[('', '全部等级')] + list(EmergencyEvent.SEVERITY_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    status = forms.ChoiceField(
        choices=[('', '全部状态')] + list(EmergencyEvent.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    granary = forms.ModelChoiceField(
        queryset=Granary.objects.filter(is_active=True),
        required=False,
        empty_label='全部粮仓',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )


class EmergencyPlanForm(forms.ModelForm):
    class Meta:
        model = EmergencyPlan
        fields = ['plan_type', 'plan_name', 'objectives', 'measures',
                  'resource_requirements', 'expected_effect', 'estimated_cost',
                  'estimated_duration_hours', 'created_by']
        widgets = {
            'plan_type': forms.Select(attrs={'class': 'form-select'}),
            'plan_name': forms.TextInput(attrs={'class': 'form-control'}),
            'objectives': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'measures': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'resource_requirements': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'expected_effect': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'estimated_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'estimated_duration_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'created_by': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resource_requirements'].required = False
        self.fields['expected_effect'].required = False
        self.fields['estimated_cost'].required = False
        self.fields['estimated_duration_hours'].required = False


class EmergencyPlanApproveForm(forms.Form):
    approved_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='审批人'
    )
    approval_opinion = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=False,
        label='审批意见'
    )


class EmergencyCommandForm(forms.ModelForm):
    class Meta:
        model = EmergencyCommand
        fields = ['command_type', 'priority', 'title', 'content', 'requirements',
                  'issuer', 'assignee', 'assignee_department', 'deadline']
        widgets = {
            'command_type': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'requirements': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'issuer': forms.TextInput(attrs={'class': 'form-control'}),
            'assignee': forms.TextInput(attrs={'class': 'form-control'}),
            'assignee_department': forms.TextInput(attrs={'class': 'form-control'}),
            'deadline': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['requirements'].required = False
        self.fields['assignee_department'].required = False
        self.fields['deadline'].required = False
        if event and not self.initial.get('deadline'):
            hours = 24 if event.severity in ('general', 'major') else 4
            default_deadline = timezone.now() + timedelta(hours=hours)
            self.initial['deadline'] = default_deadline.strftime('%Y-%m-%dT%H:%M')
        if event and not self.initial.get('priority'):
            if event.severity in ('severe', 'extreme'):
                self.initial['priority'] = 'urgent'
            elif event.severity == 'major':
                self.initial['priority'] = 'high'

    def clean_deadline(self):
        deadline = self.cleaned_data.get('deadline')
        if deadline and deadline < timezone.now():
            raise ValidationError('要求完成时间不能早于当前时间')
        return deadline


class EmergencyCommandExecuteForm(forms.Form):
    actual_start = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        label='实际开始时间',
        required=False
    )
    actual_end = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        label='实际完成时间',
        required=False
    )
    execution_result = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        label='执行结果'
    )
    feedback_attachments = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
        label='反馈附件'
    )
    acknowledged_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='执行人'
    )


class EmergencyFeedbackForm(forms.ModelForm):
    class Meta:
        model = EmergencyFeedback
        fields = ['feedback_type', 'situation_assessment', 'location', 'reporter',
                  'reporter_phone', 'content', 'measures_taken', 'needs_assistance',
                  'assistance_details', 'temperature', 'humidity', 'pest_density',
                  'affected_area', 'attachments', 'photos']
        widgets = {
            'feedback_type': forms.Select(attrs={'class': 'form-select'}),
            'situation_assessment': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'reporter': forms.TextInput(attrs={'class': 'form-control'}),
            'reporter_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'measures_taken': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'needs_assistance': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'assistance_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'temperature': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'humidity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'pest_density': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'affected_area': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'attachments': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'photos': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].required = False
        self.fields['reporter_phone'].required = False
        self.fields['measures_taken'].required = False
        self.fields['assistance_details'].required = False
        self.fields['temperature'].required = False
        self.fields['humidity'].required = False
        self.fields['pest_density'].required = False
        self.fields['affected_area'].required = False
        self.fields['attachments'].required = False
        self.fields['photos'].required = False


class EmergencyTaskForm(forms.ModelForm):
    class Meta:
        model = EmergencyTask
        fields = ['task_type', 'title', 'description', 'priority', 'assignee',
                  'assignee_department', 'assigner', 'start_time', 'due_time',
                  'expected_result']
        widgets = {
            'task_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'assignee': forms.TextInput(attrs={'class': 'form-control'}),
            'assignee_department': forms.TextInput(attrs={'class': 'form-control'}),
            'assigner': forms.TextInput(attrs={'class': 'form-control'}),
            'start_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'due_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'expected_result': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee_department'].required = False
        self.fields['start_time'].required = False
        self.fields['due_time'].required = False
        self.fields['expected_result'].required = False
        if event and not self.initial.get('due_time'):
            hours = 24 if event.severity in ('general', 'major') else 8
            default_due = timezone.now() + timedelta(hours=hours)
            self.initial['due_time'] = default_due.strftime('%Y-%m-%dT%H:%M')

    def clean_due_time(self):
        due_time = self.cleaned_data.get('due_time')
        start_time = self.cleaned_data.get('start_time')
        if due_time and start_time and due_time < start_time:
            raise ValidationError('截止时间不能早于开始时间')
        if due_time and due_time < timezone.now():
            raise ValidationError('截止时间不能早于当前时间')
        return due_time


class EmergencyTaskProgressForm(forms.ModelForm):
    class Meta:
        model = EmergencyTask
        fields = ['progress', 'actual_result', 'difficulties']
        widgets = {
            'progress': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100'}),
            'actual_result': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'difficulties': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['actual_result'].required = False
        self.fields['difficulties'].required = False

    def clean_progress(self):
        progress = self.cleaned_data.get('progress')
        if progress is not None and (progress < 0 or progress > 100):
            raise ValidationError('进度必须在0-100之间')
        return progress


class EmergencyTaskCompleteForm(forms.Form):
    actual_end = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        label='实际完成时间'
    )
    actual_result = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        label='实际成果'
    )
    completion_remark = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
        label='完成备注'
    )
    completed_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='完成确认人'
    )


class EmergencyUpgradeForm(forms.ModelForm):
    class Meta:
        model = EmergencyUpgrade
        fields = ['new_severity', 'reason', 'basis', 'additional_measures', 'requested_by']
        widgets = {
            'new_severity': forms.Select(attrs={'class': 'form-select'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'basis': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'additional_measures': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'requested_by': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['additional_measures'].required = False
        if event:
            current_severity = event.severity
            severity_order = ['general', 'major', 'severe', 'extreme']
            current_index = severity_order.index(current_severity)
            available_choices = [
                (s, label) for s, label in EmergencyEvent.SEVERITY_CHOICES
                if severity_order.index(s) > current_index
            ]
            self.fields['new_severity'].choices = available_choices

    def clean_new_severity(self):
        new_severity = self.cleaned_data.get('new_severity')
        if self.instance and self.instance.event:
            severity_order = ['general', 'major', 'severe', 'extreme']
            if severity_order.index(new_severity) <= severity_order.index(self.instance.event.severity):
                raise ValidationError('新的严重程度必须高于当前严重程度')
        return new_severity


class EmergencyUpgradeApproveForm(forms.Form):
    approved_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='审批人'
    )
    approval_opinion = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=False,
        label='审批意见'
    )
    notified_persons = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
        label='已通知人员'
    )


class EmergencyClosureForm(forms.ModelForm):
    class Meta:
        model = EmergencyClosure
        fields = ['verification_results', 'stability_assessment', 'remaining_risks',
                  'followup_actions', 'resource_usage_summary', 'lessons_learned',
                  'improvement_suggestions', 'requested_by']
        widgets = {
            'verification_results': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'stability_assessment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'remaining_risks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'followup_actions': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'resource_usage_summary': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'lessons_learned': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'improvement_suggestions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'requested_by': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['remaining_risks'].required = False
        self.fields['followup_actions'].required = False
        self.fields['resource_usage_summary'].required = False
        self.fields['lessons_learned'].required = False
        self.fields['improvement_suggestions'].required = False


class EmergencyClosureApproveForm(forms.Form):
    verified_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='核查人'
    )
    approved_by = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='批准人'
    )
    total_response_duration = forms.FloatField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
        label='总响应时长(小时)',
        required=False
    )
    total_disposal_duration = forms.FloatField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
        label='总处置时长(小时)',
        required=False
    )


class AlternativeRouteForm(forms.ModelForm):
    class Meta:
        model = AlternativeRoute
        fields = ['alternative_route', 'route_description', 'waypoints', 'distance_km',
                  'estimated_hours', 'cost_per_ton', 'transport_type', 'risk_assessment',
                  'source_granary', 'target_granary']
        widgets = {
            'alternative_route': forms.Select(attrs={'class': 'form-select'}),
            'route_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'waypoints': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'distance_km': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'estimated_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'cost_per_ton': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'transport_type': forms.Select(attrs={'class': 'form-select'}),
            'risk_assessment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'source_granary': forms.Select(attrs={'class': 'form-select'}),
            'target_granary': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['alternative_route'].required = False
        self.fields['alternative_route'].queryset = TransportRoute.objects.filter(is_active=True)
        self.fields['alternative_route'].empty_label = '自定义路线'
        self.fields['waypoints'].required = False
        self.fields['risk_assessment'].required = False
        self.fields['source_granary'].queryset = Granary.objects.filter(is_active=True)
        self.fields['target_granary'].queryset = Granary.objects.filter(is_active=True)


class ImpactAnalysisForm(forms.Form):
    analyze_granaries = forms.BooleanField(
        required=False,
        initial=True,
        label='分析受影响粮仓',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    analyze_batches = forms.BooleanField(
        required=False,
        initial=True,
        label='分析受影响批次',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    analyze_routes = forms.BooleanField(
        required=False,
        initial=True,
        label='分析受影响路径',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    analyze_executions = forms.BooleanField(
        required=False,
        initial=True,
        label='分析受影响在途任务',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    impact_radius_km = forms.FloatField(
        required=False,
        initial=50.0,
        min_value=0,
        label='影响半径(公里)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '1'})
    )