from django import forms
from django.core.exceptions import ValidationError
from .models import (
    GrainType, Granary, TemperatureHumidityLog,
    VentilationLog, PestInspection, RiskAssessment
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
