from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, DetailView
)
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.db.models import Q
from datetime import date, timedelta
import json

from .models import (
    GrainType, Granary, TemperatureHumidityLog,
    VentilationLog, PestInspection, RiskAssessment,
    Warning, DisposalTask, DisposalProgressLog,
    InventoryChangeLog, AllocationConfig, AllocationSuggestion,
    AllocationExecution, GrainSituationPrediction
)
from .forms import (
    GrainTypeForm, GranaryForm, TemperatureHumidityLogForm,
    VentilationLogForm, PestInspectionForm, RiskProcessForm,
    WarningCreateForm, DisposalTaskAssignForm, DisposalProgressForm,
    DisposalSubmitForm, DisposalReviewForm, DisposalArchiveForm, WarningFilterForm,
    InventoryChangeLogForm, AllocationConfigForm, AllocationSuggestionForm,
    AllocationSuggestionApproveForm, AllocationExecutionForm,
    PredictionGenerateForm, AllocationGenerateForm
)
from .services import (
    RiskCalculator, recalculate_risks_after_ventilation, recalculate_risks_for_granary,
    WarningService, DisposalService, WarningStatisticsService,
    GrainSituationPredictionService, InventoryService, AllocationService,
    PredictionStatisticsService
)


def dashboard(request):
    today = date.today()
    thirty_days_ago = today - timedelta(days=29)

    granaries = Granary.objects.filter(is_active=True)
    total_granaries = granaries.count()

    latest_ids = {}
    all_assessments = RiskAssessment.objects.filter(
        assess_date__lte=today
    ).select_related('granary').order_by('granary_id', '-assess_date')
    for a in all_assessments:
        if a.granary_id not in latest_ids:
            latest_ids[a.granary_id] = a.id
    latest_assessments = RiskAssessment.objects.filter(id__in=latest_ids.values()).select_related('granary')

    high_count = 0
    medium_count = 0
    low_count = 0
    pending_count = 0
    for a in latest_assessments:
        if a.status == 'pending':
            pending_count += 1
        if a.risk_level == 'high':
            high_count += 1
        elif a.risk_level == 'medium':
            medium_count += 1
        else:
            low_count += 1

    risk_ranking = RiskAssessment.objects.filter(
        assess_date=today
    ).select_related('granary').order_by('-overall_risk_score')[:10]

    if not risk_ranking:
        latest_date = RiskAssessment.objects.order_by('-assess_date').values_list('assess_date', flat=True).first()
        if latest_date:
            risk_ranking = RiskAssessment.objects.filter(
                assess_date=latest_date
            ).select_related('granary').order_by('-overall_risk_score')[:10]

    recent_logs = TemperatureHumidityLog.objects.select_related('granary').order_by('-record_date')[:10]
    recent_ventilations = VentilationLog.objects.select_related('granary').order_by('-start_time')[:5]
    recent_pests = PestInspection.objects.select_related('granary').order_by('-inspect_date')[:5]

    return render(request, 'dashboard.html', {
        'total_granaries': total_granaries,
        'high_count': high_count,
        'medium_count': medium_count,
        'low_count': low_count,
        'pending_count': pending_count,
        'risk_ranking': risk_ranking,
        'recent_logs': recent_logs,
        'recent_ventilations': recent_ventilations,
        'recent_pests': recent_pests,
        'granaries': granaries,
        'today': today,
    })


def risk_ranking_chart(request):
    today = date.today()
    assessments = RiskAssessment.objects.filter(
        assess_date=today
    ).select_related('granary').order_by('-overall_risk_score')

    if not assessments:
        latest_date = RiskAssessment.objects.order_by('-assess_date').values_list('assess_date', flat=True).first()
        if latest_date:
            assessments = RiskAssessment.objects.filter(
                assess_date=latest_date
            ).select_related('granary').order_by('-overall_risk_score')

    labels = []
    mold_scores = []
    pest_scores = []
    overall_scores = []
    colors = []

    for a in assessments:
        labels.append(a.granary.code)
        mold_scores.append(a.mold_risk_score)
        pest_scores.append(a.pest_risk_score)
        overall_scores.append(a.overall_risk_score)
        if a.risk_level == 'high':
            colors.append('rgba(220, 53, 69, 0.8)')
        elif a.risk_level == 'medium':
            colors.append('rgba(255, 193, 7, 0.8)')
        else:
            colors.append('rgba(40, 167, 69, 0.8)')

    return JsonResponse({
        'labels': labels,
        'mold_scores': mold_scores,
        'pest_scores': pest_scores,
        'overall_scores': overall_scores,
        'colors': colors,
    })


def risk_trend_data(request):
    granary_id = request.GET.get('granary_id')
    days = int(request.GET.get('days', 30))
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    query = RiskAssessment.objects.filter(
        assess_date__gte=start_date,
        assess_date__lte=end_date
    ).select_related('granary').order_by('assess_date')

    if granary_id and granary_id != 'all':
        query = query.filter(granary_id=granary_id)

    assessments = list(query)

    all_dates = []
    for i in range(days):
        all_dates.append(start_date + timedelta(days=i))

    if granary_id and granary_id != 'all':
        granary = Granary.objects.filter(id=granary_id).first()
        labels = [d.strftime('%m-%d') for d in all_dates]
        overall = []
        mold = []
        pest = []
        for d in all_dates:
            a = next((x for x in assessments if x.assess_date == d), None)
            if a:
                overall.append(a.overall_risk_score)
                mold.append(a.mold_risk_score)
                pest.append(a.pest_risk_score)
            else:
                overall.append(None)
                mold.append(None)
                pest.append(None)
        datasets = {
            'granary': granary.code if granary else '',
            'labels': labels,
            'overall': overall,
            'mold': mold,
            'pest': pest,
        }
    else:
        granaries = Granary.objects.filter(is_active=True)[:8]
        labels = [d.strftime('%m-%d') for d in all_dates]
        datasets = []
        for g in granaries:
            data = []
            for d in all_dates:
                a = next((x for x in assessments if x.granary_id == g.id and x.assess_date == d), None)
                data.append(a.overall_risk_score if a else None)
            datasets.append({
                'label': g.code,
                'data': data,
                'borderColor': f'rgba({(g.id * 50) % 255}, {(g.id * 80) % 255}, {(g.id * 120) % 255}, 1)',
                'backgroundColor': f'rgba({(g.id * 50) % 255}, {(g.id * 80) % 255}, {(g.id * 120) % 255}, 0.1)',
                'fill': False,
                'tension': 0.3,
            })
        datasets = {'labels': labels, 'lines': datasets}

    return JsonResponse(datasets, safe=False)


def temp_humidity_trend(request):
    granary_id = request.GET.get('granary_id')
    days = int(request.GET.get('days', 30))
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    query = TemperatureHumidityLog.objects.filter(
        record_date__gte=start_date,
        record_date__lte=end_date
    ).select_related('granary').order_by('record_date')

    if granary_id and granary_id != 'all':
        query = query.filter(granary_id=granary_id)

    logs = list(query)
    all_dates = []
    for i in range(days):
        all_dates.append(start_date + timedelta(days=i))

    labels = [d.strftime('%m-%d') for d in all_dates]

    if granary_id and granary_id != 'all':
        temps = []
        hums = []
        for d in all_dates:
            log = next((x for x in logs if x.record_date == d), None)
            if log:
                temps.append(log.temperature)
                hums.append(log.humidity)
            else:
                temps.append(None)
                hums.append(None)
        data = {'labels': labels, 'temperatures': temps, 'humidities': hums}
    else:
        granaries = Granary.objects.filter(is_active=True)[:5]
        lines = []
        for g in granaries:
            t_data = []
            for d in all_dates:
                log = next((x for x in logs if x.granary_id == g.id and x.record_date == d), None)
                t_data.append(log.temperature if log else None)
            lines.append({
                'label': g.code,
                'data': t_data,
                'borderColor': f'rgba({(g.id * 50 + 100) % 255}, {(g.id * 80 + 50) % 255}, {(g.id * 120) % 255}, 1)',
                'fill': False,
                'tension': 0.3,
            })
        data = {'labels': labels, 'lines': lines}

    return JsonResponse(data, safe=False)


# -------------------- GrainType Views --------------------
class GrainTypeListView(ListView):
    model = GrainType
    template_name = 'grain_type/list.html'
    context_object_name = 'grain_types'
    ordering = ['-created_at']


class GrainTypeCreateView(CreateView):
    model = GrainType
    form_class = GrainTypeForm
    template_name = 'grain_type/form.html'
    success_url = reverse_lazy('grain_type_list')

    def form_valid(self, form):
        messages.success(self.request, '粮食品类创建成功')
        return super().form_valid(form)


class GrainTypeUpdateView(UpdateView):
    model = GrainType
    form_class = GrainTypeForm
    template_name = 'grain_type/form.html'
    success_url = reverse_lazy('grain_type_list')

    def form_valid(self, form):
        messages.success(self.request, '粮食品类更新成功')
        return super().form_valid(form)


class GrainTypeDeleteView(DeleteView):
    model = GrainType
    template_name = 'grain_type/confirm_delete.html'
    success_url = reverse_lazy('grain_type_list')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.granaries.exists():
            messages.error(request, '该品类下有粮仓，无法删除')
            return redirect('grain_type_list')
        messages.success(request, '粮食品类删除成功')
        return super().delete(request, *args, **kwargs)


# -------------------- Granary Views --------------------
class GranaryListView(ListView):
    model = Granary
    template_name = 'granary/list.html'
    context_object_name = 'granaries'
    ordering = ['code']

    def get_queryset(self):
        qs = super().get_queryset().select_related('grain_type')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['query'] = self.request.GET.get('q', '')
        return ctx


class GranaryDetailView(DetailView):
    model = Granary
    template_name = 'granary/detail.html'
    context_object_name = 'granary'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx['th_logs'] = obj.th_logs.all()[:14]
        ctx['vent_logs'] = obj.ventilation_logs.all()[:10]
        ctx['pest_logs'] = obj.pest_inspections.all()[:10]
        ctx['risk_assessments'] = obj.risk_assessments.all()[:14]
        ctx['latest_risk'] = obj.risk_assessments.order_by('-assess_date').first()
        ctx['consecutive_days'] = obj.get_consecutive_days()
        ctx['has_continuous'] = obj.has_continuous_data(3)
        return ctx


class GranaryCreateView(CreateView):
    model = Granary
    form_class = GranaryForm
    template_name = 'granary/form.html'
    success_url = reverse_lazy('granary_list')

    def form_valid(self, form):
        messages.success(self.request, '粮仓创建成功')
        return super().form_valid(form)


class GranaryUpdateView(UpdateView):
    model = Granary
    form_class = GranaryForm
    template_name = 'granary/form.html'
    success_url = reverse_lazy('granary_list')

    def form_valid(self, form):
        old_vent = Granary.objects.get(pk=self.object.pk).ventilation_status
        response = super().form_valid(form)
        new_vent = self.object.ventilation_status
        if old_vent != new_vent:
            try:
                recalculate_risks_for_granary(self.object)
                messages.success(self.request, '粮仓更新成功，通风状态已变更，风险评分已重新计算')
            except Exception:
                messages.success(self.request, '粮仓更新成功，通风状态已变更，但风险评分重算失败')
        else:
            messages.success(self.request, '粮仓更新成功')
        return response


class GranaryDeleteView(DeleteView):
    model = Granary
    template_name = 'granary/confirm_delete.html'
    success_url = reverse_lazy('granary_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, '粮仓删除成功')
        return super().delete(request, *args, **kwargs)


# -------------------- TemperatureHumidityLog Views --------------------
class THLogListView(ListView):
    model = TemperatureHumidityLog
    template_name = 'th_log/list.html'
    context_object_name = 'logs'
    ordering = ['-record_date']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('granary')
        granary_id = self.request.GET.get('granary')
        if granary_id:
            qs = qs.filter(granary_id=granary_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['granaries'] = Granary.objects.filter(is_active=True)
        ctx['selected_granary'] = self.request.GET.get('granary', '')
        return ctx


class THLogCreateView(CreateView):
    model = TemperatureHumidityLog
    form_class = TemperatureHumidityLogForm
    template_name = 'th_log/form.html'
    success_url = reverse_lazy('th_log_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        try:
            assess = RiskCalculator.assess_granary(self.object.granary, self.object.record_date)
            existing = RiskAssessment.objects.filter(
                granary=self.object.granary, assess_date=self.object.record_date
            ).first()
            if existing:
                existing.mold_risk_score = assess.mold_risk_score
                existing.pest_risk_score = assess.pest_risk_score
                existing.ventilation_factor = assess.ventilation_factor
                existing.overall_risk_score = assess.overall_risk_score
                existing.risk_level = assess.risk_level
                existing.is_formal = assess.is_formal
                existing.consecutive_days = assess.consecutive_days
                existing.save()
            else:
                assess.save()
        except Exception:
            pass
        messages.success(self.request, '温湿度记录添加成功，风险评分已更新')
        return response


class THLogUpdateView(UpdateView):
    model = TemperatureHumidityLog
    form_class = TemperatureHumidityLogForm
    template_name = 'th_log/form.html'
    success_url = reverse_lazy('th_log_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        try:
            assess = RiskCalculator.assess_granary(self.object.granary, self.object.record_date)
            existing = RiskAssessment.objects.filter(
                granary=self.object.granary, assess_date=self.object.record_date
            ).first()
            if existing:
                existing.mold_risk_score = assess.mold_risk_score
                existing.pest_risk_score = assess.pest_risk_score
                existing.ventilation_factor = assess.ventilation_factor
                existing.overall_risk_score = assess.overall_risk_score
                existing.risk_level = assess.risk_level
                existing.is_formal = assess.is_formal
                existing.consecutive_days = assess.consecutive_days
                existing.save()
        except Exception:
            pass
        messages.success(self.request, '温湿度记录更新成功，风险评分已更新')
        return response


class THLogDeleteView(DeleteView):
    model = TemperatureHumidityLog
    template_name = 'th_log/confirm_delete.html'
    success_url = reverse_lazy('th_log_list')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, '温湿度记录删除成功')
        return super().delete(request, *args, **kwargs)


# -------------------- VentilationLog Views --------------------
class VentilationLogListView(ListView):
    model = VentilationLog
    template_name = 'ventilation/list.html'
    context_object_name = 'logs'
    ordering = ['-start_time']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('granary')
        granary_id = self.request.GET.get('granary')
        if granary_id:
            qs = qs.filter(granary_id=granary_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['granaries'] = Granary.objects.filter(is_active=True)
        ctx['selected_granary'] = self.request.GET.get('granary', '')
        return ctx


class VentilationLogCreateView(CreateView):
    model = VentilationLog
    form_class = VentilationLogForm
    template_name = 'ventilation/form.html'
    success_url = reverse_lazy('ventilation_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        try:
            recalculate_risks_after_ventilation(self.object)
            messages.success(self.request, '通风记录添加成功，风险评分已重新计算')
        except Exception as e:
            messages.success(self.request, f'通风记录添加成功，但风险评分重算失败: {e}')
        return response


class VentilationLogUpdateView(UpdateView):
    model = VentilationLog
    form_class = VentilationLogForm
    template_name = 'ventilation/form.html'
    success_url = reverse_lazy('ventilation_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        try:
            recalculate_risks_after_ventilation(self.object)
            messages.success(self.request, '通风记录更新成功，风险评分已重新计算')
        except Exception as e:
            messages.success(self.request, f'通风记录更新成功，但风险评分重算失败: {e}')
        return response


class VentilationLogDeleteView(DeleteView):
    model = VentilationLog
    template_name = 'ventilation/confirm_delete.html'
    success_url = reverse_lazy('ventilation_list')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, '通风记录删除成功')
        return super().delete(request, *args, **kwargs)


# -------------------- PestInspection Views --------------------
class PestInspectionListView(ListView):
    model = PestInspection
    template_name = 'pest/list.html'
    context_object_name = 'inspections'
    ordering = ['-inspect_date']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('granary')
        granary_id = self.request.GET.get('granary')
        if granary_id:
            qs = qs.filter(granary_id=granary_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['granaries'] = Granary.objects.filter(is_active=True)
        ctx['selected_granary'] = self.request.GET.get('granary', '')
        return ctx


class PestInspectionCreateView(CreateView):
    model = PestInspection
    form_class = PestInspectionForm
    template_name = 'pest/form.html'
    success_url = reverse_lazy('pest_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        try:
            assess = RiskCalculator.assess_granary(self.object.granary, self.object.inspect_date)
            existing = RiskAssessment.objects.filter(
                granary=self.object.granary, assess_date=self.object.inspect_date
            ).first()
            if existing:
                existing.mold_risk_score = assess.mold_risk_score
                existing.pest_risk_score = assess.pest_risk_score
                existing.ventilation_factor = assess.ventilation_factor
                existing.overall_risk_score = assess.overall_risk_score
                existing.risk_level = assess.risk_level
                existing.is_formal = assess.is_formal
                existing.consecutive_days = assess.consecutive_days
                existing.save()
            else:
                assess.save()
        except Exception:
            pass
        messages.success(self.request, '虫害抽检记录添加成功，风险评分已更新')
        return response


class PestInspectionUpdateView(UpdateView):
    model = PestInspection
    form_class = PestInspectionForm
    template_name = 'pest/form.html'
    success_url = reverse_lazy('pest_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        try:
            assess = RiskCalculator.assess_granary(self.object.granary, self.object.inspect_date)
            existing = RiskAssessment.objects.filter(
                granary=self.object.granary, assess_date=self.object.inspect_date
            ).first()
            if existing:
                existing.mold_risk_score = assess.mold_risk_score
                existing.pest_risk_score = assess.pest_risk_score
                existing.ventilation_factor = assess.ventilation_factor
                existing.overall_risk_score = assess.overall_risk_score
                existing.risk_level = assess.risk_level
                existing.is_formal = assess.is_formal
                existing.consecutive_days = assess.consecutive_days
                existing.save()
        except Exception:
            pass
        messages.success(self.request, '虫害抽检记录更新成功，风险评分已更新')
        return response


class PestInspectionDeleteView(DeleteView):
    model = PestInspection
    template_name = 'pest/confirm_delete.html'
    success_url = reverse_lazy('pest_list')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, '虫害抽检记录删除成功')
        return super().delete(request, *args, **kwargs)


# -------------------- RiskAssessment Views --------------------
class RiskAssessmentListView(ListView):
    model = RiskAssessment
    template_name = 'risk/list.html'
    context_object_name = 'assessments'
    ordering = ['-assess_date', '-overall_risk_score']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('granary')
        level = self.request.GET.get('level')
        status = self.request.GET.get('status')
        if level:
            qs = qs.filter(risk_level=level)
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['selected_level'] = self.request.GET.get('level', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['today'] = date.today()
        return ctx


class RiskAssessmentDetailView(DetailView):
    model = RiskAssessment
    template_name = 'risk/detail.html'
    context_object_name = 'assessment'


def generate_risk_assessments(request):
    target_date = date.today()
    date_str = request.POST.get('assess_date')
    if date_str:
        try:
            from datetime import datetime
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            target_date = date.today()

    count = 0
    granaries = Granary.objects.filter(is_active=True)
    for granary in granaries:
        try:
            assess = RiskCalculator.assess_granary(granary, target_date)
            existing = RiskAssessment.objects.filter(
                granary=granary, assess_date=target_date
            ).first()
            if existing:
                existing.mold_risk_score = assess.mold_risk_score
                existing.pest_risk_score = assess.pest_risk_score
                existing.ventilation_factor = assess.ventilation_factor
                existing.overall_risk_score = assess.overall_risk_score
                existing.risk_level = assess.risk_level
                existing.is_formal = assess.is_formal
                existing.consecutive_days = assess.consecutive_days
                existing.save()
            else:
                assess.save()
            count += 1
        except Exception:
            pass

    messages.success(request, f'成功为 {count} 个粮仓生成/更新风险评估（{target_date}）')
    return redirect('risk_list')


def process_risk(request, pk):
    assessment = get_object_or_404(RiskAssessment, pk=pk)
    if request.method == 'POST':
        form = RiskProcessForm(request.POST, instance=assessment)
        if form.is_valid():
            form.save()
            messages.success(request, '风险处置状态已更新')
            return redirect('risk_detail', pk=assessment.pk)
    else:
        form = RiskProcessForm(instance=assessment)
    return render(request, 'risk/process.html', {
        'form': form,
        'assessment': assessment,
    })


# -------------------- Warning Views --------------------
class WarningListView(ListView):
    model = Warning
    template_name = 'warning/list.html'
    context_object_name = 'warnings'
    ordering = ['-warning_time']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('granary')
        level = self.request.GET.get('level')
        status = self.request.GET.get('status')
        granary_id = self.request.GET.get('granary')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if level:
            qs = qs.filter(warning_level=level)
        if status:
            qs = qs.filter(status=status)
        if granary_id:
            qs = qs.filter(granary_id=granary_id)
        if start_date:
            qs = qs.filter(warning_time__date__gte=start_date)
        if end_date:
            qs = qs.filter(warning_time__date__lte=end_date)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filter_form = WarningFilterForm(self.request.GET or None)
        ctx['filter_form'] = filter_form
        ctx['today'] = date.today()
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        ctx['query_string'] = query_params.urlencode()
        if ctx['query_string']:
            ctx['query_string'] = '&' + ctx['query_string']
        return ctx


class WarningDetailView(DetailView):
    model = Warning
    template_name = 'warning/detail.html'
    context_object_name = 'warning'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tasks'] = self.object.disposal_tasks.select_related('warning').order_by('-assigned_time')
        ctx['notify_logs'] = self.object.notify_logs.all()[:20]
        return ctx


def warning_create(request):
    if request.method == 'POST':
        form = WarningCreateForm(request.POST)
        if form.is_valid():
            warning = form.save(commit=False)
            warning.trigger_type = 'manual'
            warning.save()
            WarningService.create_notify_log(warning)
            messages.success(request, '手动预警创建成功')
            return redirect('warning_detail', pk=warning.pk)
    else:
        form = WarningCreateForm()
    return render(request, 'warning/form.html', {'form': form, 'title': '创建手动预警'})


def generate_warnings(request):
    target_date = date.today()
    date_str = request.POST.get('warn_date')
    if date_str:
        try:
            from datetime import datetime
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            target_date = date.today()
    created = WarningService.generate_warnings_for_date(target_date)
    messages.success(request, f'成功生成 {len(created)} 条预警记录（{target_date}）')
    return redirect('warning_list')


def check_overdue_warnings(request):
    overdue_w, overdue_t = WarningService.check_and_update_overdue()
    messages.success(request, f'检测完成：{overdue_w} 条预警超时，{overdue_t} 个任务超时')
    return redirect('warning_list')


# -------------------- DisposalTask Views --------------------
def task_assign(request, warning_pk):
    warning = get_object_or_404(Warning, pk=warning_pk)
    if request.method == 'POST':
        form = DisposalTaskAssignForm(request.POST, warning=warning)
        if form.is_valid():
            task = DisposalService.assign_task(
                warning=warning,
                task_title=form.cleaned_data['task_title'],
                assignee=form.cleaned_data['assignee'],
                assigner=form.cleaned_data.get('assigner', '系统'),
                deadline=form.cleaned_data['deadline'],
                task_description=form.cleaned_data.get('task_description'),
                priority=form.cleaned_data.get('priority'),
            )
            messages.success(request, f'处置任务已分派给 {task.assignee}')
            return redirect('task_detail', pk=task.pk)
    else:
        form = DisposalTaskAssignForm(warning=warning)
    return render(request, 'warning/task_assign.html', {'form': form, 'warning': warning})


class TaskDetailView(DetailView):
    model = DisposalTask
    template_name = 'warning/task_detail.html'
    context_object_name = 'task'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['progress_logs'] = self.object.progress_logs.all()
        ctx['progress_form'] = DisposalProgressForm()
        ctx['submit_form'] = DisposalSubmitForm()
        ctx['review_form'] = DisposalReviewForm()
        ctx['archive_form'] = DisposalArchiveForm()
        return ctx


def task_update_progress(request, pk):
    task = get_object_or_404(DisposalTask, pk=pk)
    if request.method == 'POST':
        form = DisposalProgressForm(request.POST)
        if form.is_valid():
            DisposalService.update_progress(
                task=task,
                progress_percent=form.cleaned_data['progress_percent'],
                description=form.cleaned_data['progress_description'],
                operator=form.cleaned_data['operator'],
                remark=form.cleaned_data.get('remark'),
            )
            messages.success(request, '进度更新成功')
            return redirect('task_detail', pk=task.pk)
    return redirect('task_detail', pk=task.pk)


def task_submit_review(request, pk):
    task = get_object_or_404(DisposalTask, pk=pk)
    if request.method == 'POST':
        form = DisposalSubmitForm(request.POST)
        if form.is_valid():
            DisposalService.submit_for_review(
                task=task,
                disposal_measures=form.cleaned_data['disposal_measures'],
                disposal_result=form.cleaned_data['disposal_result'],
                operator=form.cleaned_data['operator'],
                attachment=form.cleaned_data.get('disposal_attachment'),
            )
            messages.success(request, '已提交复查')
            return redirect('task_detail', pk=task.pk)
    return redirect('task_detail', pk=task.pk)


def task_review(request, pk):
    task = get_object_or_404(DisposalTask, pk=pk)
    if request.method == 'POST':
        form = DisposalReviewForm(request.POST)
        if form.is_valid():
            passed = form.cleaned_data['passed'] == 'True'
            DisposalService.review_task(
                task=task,
                reviewer=form.cleaned_data['reviewer'],
                passed=passed,
                opinion=form.cleaned_data.get('opinion'),
            )
            messages.success(request, f'复查{"通过" if passed else "不通过"}')
            return redirect('task_detail', pk=task.pk)
    return redirect('task_detail', pk=task.pk)


def task_redo(request, pk):
    task = get_object_or_404(DisposalTask, pk=pk)
    if request.method == 'POST':
        operator = request.POST.get('operator', '系统')
        DisposalService.redo_task(task, operator)
        messages.success(request, '任务已重新开启处置')
    return redirect('task_detail', pk=task.pk)


def task_archive(request, pk):
    task = get_object_or_404(DisposalTask, pk=pk)
    if request.method == 'POST':
        form = DisposalArchiveForm(request.POST)
        if form.is_valid():
            try:
                DisposalService.archive_task(
                    task=task,
                    archived_by=form.cleaned_data['archived_by'],
                    remark=form.cleaned_data.get('remark'),
                )
                messages.success(request, '任务已归档')
            except ValueError as e:
                messages.error(request, str(e))
            return redirect('task_detail', pk=task.pk)
    return redirect('task_detail', pk=task.pk)


class TaskListView(ListView):
    model = DisposalTask
    template_name = 'warning/task_list.html'
    context_object_name = 'tasks'
    ordering = ['-assigned_time']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('warning__granary')
        status = self.request.GET.get('status')
        assignee = self.request.GET.get('assignee')
        if status:
            qs = qs.filter(status=status)
        if assignee:
            qs = qs.filter(assignee__icontains=assignee)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_assignee'] = self.request.GET.get('assignee', '')
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        ctx['query_string'] = query_params.urlencode()
        if ctx['query_string']:
            ctx['query_string'] = '&' + ctx['query_string']
        return ctx


# -------------------- Warning Dashboard Views --------------------
def warning_dashboard(request):
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    days = int(request.GET.get('days', 30))

    start_date = None
    end_date = None
    if start_date_str:
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    if end_date_str:
        from datetime import datetime
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    overview = WarningStatisticsService.get_overview_stats(start_date, end_date)
    by_granary = WarningStatisticsService.get_by_granary(start_date, end_date)
    trend = WarningStatisticsService.get_by_date_trend(days)
    efficiency = WarningStatisticsService.get_disposal_efficiency(start_date, end_date)

    return render(request, 'warning/dashboard.html', {
        'overview': overview,
        'by_granary': by_granary,
        'trend': trend,
        'efficiency': efficiency,
        'start_date': start_date_str or '',
        'end_date': end_date_str or '',
        'days': days,
    })


def warning_trend_api(request):
    days = int(request.GET.get('days', 30))
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    start_date = None
    end_date = None
    if start_date_str:
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    if end_date_str:
        from datetime import datetime
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    trend = WarningStatisticsService.get_by_date_trend(days, start_date, end_date)
    return JsonResponse({
        'labels': [t['label'] for t in trend],
        'level1': [t['level1'] for t in trend],
        'level2': [t['level2'] for t in trend],
        'level3': [t['level3'] for t in trend],
        'total': [t['total'] for t in trend],
    })


def warning_by_granary_api(request):
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    start_date = None
    end_date = None
    if start_date_str:
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    if end_date_str:
        from datetime import datetime
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    data = WarningStatisticsService.get_by_granary(start_date, end_date)
    return JsonResponse({
        'labels': [d['code'] for d in data],
        'level1': [d['level1'] for d in data],
        'level2': [d['level2'] for d in data],
        'level3': [d['level3'] for d in data],
        'total': [d['total'] for d in data],
    })


# -------------------- Prediction Views --------------------
def prediction_dashboard(request):
    horizon_days = int(request.GET.get('horizon', 7))
    granary_id = request.GET.get('granary', '')

    overview = PredictionStatisticsService.get_overview_stats(horizon_days)
    risk_dist = PredictionStatisticsService.get_risk_distribution(horizon_days)
    inv_dist = PredictionStatisticsService.get_inventory_distribution(horizon_days)

    high_risk_predictions = GrainSituationPredictionService.get_high_risk_predictions(horizon_days)
    inventory_pressure = GrainSituationPredictionService.get_inventory_pressure_predictions(horizon_days)

    generate_form = PredictionGenerateForm(initial={
        'horizon_days': horizon_days,
        'granary': granary_id if granary_id else None,
    })

    today = date.today()
    latest_predictions = GrainSituationPrediction.objects.filter(
        prediction_date=today,
        horizon_days=horizon_days
    ).select_related('granary').order_by('-predicted_overall_risk')

    if granary_id and granary_id != 'all':
        latest_predictions = latest_predictions.filter(granary_id=granary_id)

    granaries = Granary.objects.filter(is_active=True)

    return render(request, 'prediction/dashboard.html', {
        'overview': overview,
        'risk_dist': risk_dist,
        'inv_dist': inv_dist,
        'high_risk_predictions': high_risk_predictions,
        'inventory_pressure': inventory_pressure,
        'generate_form': generate_form,
        'latest_predictions': latest_predictions,
        'granaries': granaries,
        'horizon_days': horizon_days,
        'selected_granary': granary_id,
    })


def generate_predictions(request):
    if request.method == 'POST':
        form = PredictionGenerateForm(request.POST)
        if form.is_valid():
            horizon_days = int(form.cleaned_data['horizon_days'])
            granary = form.cleaned_data['granary']
            prediction_date = date.today()
            predictions = GrainSituationPredictionService.predict_all_granaries(
                prediction_date, horizon_days, granary
            )
            count = len(predictions)
            if granary:
                messages.success(request, f'成功为粮仓 {granary.code} 生成 {count} 条预测记录（{horizon_days}天）')
            else:
                messages.success(request, f'成功为 {count} 个粮仓生成预测记录（{horizon_days}天）')
    return redirect('prediction_dashboard')


def prediction_list(request):
    horizon_days = int(request.GET.get('horizon', 7))
    granary_id = request.GET.get('granary', '')
    risk_level = request.GET.get('risk_level', '')

    queryset = GrainSituationPrediction.objects.select_related('granary')

    if horizon_days:
        queryset = queryset.filter(horizon_days=horizon_days)
    if granary_id and granary_id != 'all':
        queryset = queryset.filter(granary_id=granary_id)
    if risk_level:
        queryset = queryset.filter(predicted_risk_level=risk_level)

    return render(request, 'prediction/list.html', {
        'predictions': queryset[:100],
        'horizon_days': horizon_days,
        'selected_granary': granary_id,
        'selected_risk': risk_level,
        'granaries': Granary.objects.filter(is_active=True),
    })


def prediction_detail(request, pk):
    prediction = get_object_or_404(GrainSituationPrediction, pk=pk)
    granary = prediction.granary
    history = GrainSituationPrediction.objects.filter(
        granary=granary,
        horizon_days=prediction.horizon_days
    ).select_related('granary').order_by('-prediction_date')[:30]

    return render(request, 'prediction/detail.html', {
        'prediction': prediction,
        'granary': granary,
        'history': history,
    })


# -------------------- Inventory Change Views --------------------
class InventoryChangeLogListView(ListView):
    model = InventoryChangeLog
    template_name = 'inventory/list.html'
    context_object_name = 'logs'
    ordering = ['-change_date', '-created_at']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('granary', 'grain_type', 'related_allocation')
        granary_id = self.request.GET.get('granary')
        change_type = self.request.GET.get('change_type')
        if granary_id:
            qs = qs.filter(granary_id=granary_id)
        if change_type:
            qs = qs.filter(change_type=change_type)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['granaries'] = Granary.objects.filter(is_active=True)
        ctx['selected_granary'] = self.request.GET.get('granary', '')
        ctx['selected_type'] = self.request.GET.get('change_type', '')
        return ctx


class InventoryChangeLogCreateView(CreateView):
    model = InventoryChangeLog
    form_class = InventoryChangeLogForm
    template_name = 'inventory/form.html'
    success_url = reverse_lazy('inventory_list')

    def form_valid(self, form):
        try:
            log = InventoryService.create_change_log(
                granary=form.cleaned_data['granary'],
                change_type=form.cleaned_data['change_type'],
                quantity=form.cleaned_data['quantity'],
                grain_type=form.cleaned_data.get('grain_type'),
                operator=form.cleaned_data.get('operator'),
                remark=form.cleaned_data.get('remark'),
            )
            messages.success(self.request, '库存变动记录创建成功')
            return redirect(self.success_url)
        except ValueError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)


# -------------------- Allocation Config Views --------------------
class AllocationConfigListView(ListView):
    model = AllocationConfig
    template_name = 'allocation/config_list.html'
    context_object_name = 'configs'
    ordering = ['-is_default', '-created_at']


class AllocationConfigCreateView(CreateView):
    model = AllocationConfig
    form_class = AllocationConfigForm
    template_name = 'allocation/config_form.html'
    success_url = reverse_lazy('allocation_config_list')

    def form_valid(self, form):
        if form.cleaned_data.get('is_default'):
            AllocationConfig.objects.update(is_default=False)
        messages.success(self.request, '调拨配置创建成功')
        return super().form_valid(form)


class AllocationConfigUpdateView(UpdateView):
    model = AllocationConfig
    form_class = AllocationConfigForm
    template_name = 'allocation/config_form.html'
    success_url = reverse_lazy('allocation_config_list')

    def form_valid(self, form):
        if form.cleaned_data.get('is_default'):
            AllocationConfig.objects.exclude(pk=self.object.pk).update(is_default=False)
        messages.success(self.request, '调拨配置更新成功')
        return super().form_valid(form)


class AllocationConfigDeleteView(DeleteView):
    model = AllocationConfig
    template_name = 'allocation/config_confirm_delete.html'
    success_url = reverse_lazy('allocation_config_list')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_default:
            messages.error(request, '默认配置不能删除，请先设置其他配置为默认')
            return redirect(self.success_url)
        messages.success(request, '调拨配置删除成功')
        return super().delete(request, *args, **kwargs)


# -------------------- Allocation Suggestion Views --------------------
class AllocationSuggestionListView(ListView):
    model = AllocationSuggestion
    template_name = 'allocation/suggestion_list.html'
    context_object_name = 'suggestions'
    ordering = ['-priority_score', '-created_at']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('source_granary', 'target_granary', 'grain_type', 'config')
        status = self.request.GET.get('status')
        priority = self.request.GET.get('priority')
        if status:
            qs = qs.filter(status=status)
        if priority:
            qs = qs.filter(priority_level=priority)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_priority'] = self.request.GET.get('priority', '')
        ctx['generate_form'] = AllocationGenerateForm()
        return ctx


def generate_allocation_suggestions(request):
    if request.method == 'POST':
        form = AllocationGenerateForm(request.POST)
        if form.is_valid():
            config = form.cleaned_data['config']
            grain_type = form.cleaned_data.get('grain_type')
            try:
                suggestions = AllocationService.generate_allocation_suggestions(config, grain_type)
                auto_approved = sum(1 for s in suggestions if s.status == 'approved')
                messages.success(request, f'成功生成 {len(suggestions)} 条调拨建议，其中 {auto_approved} 条已自动批准')
            except ValueError as e:
                messages.error(request, str(e))
    return redirect('allocation_suggestion_list')


def allocation_suggestion_detail(request, pk):
    suggestion = get_object_or_404(AllocationSuggestion, pk=pk)
    approve_form = AllocationSuggestionApproveForm()
    return render(request, 'allocation/suggestion_detail.html', {
        'suggestion': suggestion,
        'approve_form': approve_form,
    })


def approve_allocation_suggestion(request, pk):
    suggestion = get_object_or_404(AllocationSuggestion, pk=pk)
    if request.method == 'POST':
        form = AllocationSuggestionApproveForm(request.POST)
        if form.is_valid():
            try:
                execution = AllocationService.approve_suggestion(
                    suggestion,
                    approved_by=form.cleaned_data['approved_by'],
                    approval_opinion=form.cleaned_data.get('approval_opinion'),
                )
                messages.success(request, f'调拨建议已批准，执行单号：{execution.execution_no}')
                return redirect('allocation_execution_detail', pk=execution.pk)
            except ValueError as e:
                messages.error(request, str(e))
    return redirect('allocation_suggestion_detail', pk=pk)


def reject_allocation_suggestion(request, pk):
    suggestion = get_object_or_404(AllocationSuggestion, pk=pk)
    if request.method == 'POST':
        form = AllocationSuggestionApproveForm(request.POST)
        if form.is_valid():
            try:
                AllocationService.reject_suggestion(
                    suggestion,
                    approved_by=form.cleaned_data['approved_by'],
                    approval_opinion=form.cleaned_data.get('approval_opinion'),
                )
                messages.success(request, '调拨建议已拒绝')
            except ValueError as e:
                messages.error(request, str(e))
    return redirect('allocation_suggestion_detail', pk=pk)


# -------------------- Allocation Execution Views --------------------
class AllocationExecutionListView(ListView):
    model = AllocationExecution
    template_name = 'allocation/execution_list.html'
    context_object_name = 'executions'
    ordering = ['-created_at']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('suggestion__source_granary', 'suggestion__target_granary')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['selected_status'] = self.request.GET.get('status', '')
        return ctx


def allocation_execution_detail(request, pk):
    execution = get_object_or_404(AllocationExecution, pk=pk)
    form = AllocationExecutionForm(instance=execution)
    return render(request, 'allocation/execution_detail.html', {
        'execution': execution,
        'form': form,
    })


def update_allocation_execution(request, pk):
    execution = get_object_or_404(AllocationExecution, pk=pk)
    if request.method == 'POST':
        form = AllocationExecutionForm(request.POST, instance=execution)
        if form.is_valid():
            form.save()
            messages.success(request, '调拨执行信息已更新')
            return redirect('allocation_execution_detail', pk=pk)
    return redirect('allocation_execution_detail', pk=pk)


def update_execution_status(request, pk):
    execution = get_object_or_404(AllocationExecution, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status')
        operator = request.POST.get('operator', '系统')
        try:
            AllocationService.update_execution_status(
                execution,
                status=status,
                operator=operator,
            )
            messages.success(request, f'状态已更新为：{execution.get_status_display()}')
        except Exception as e:
            messages.error(request, f'状态更新失败：{str(e)}')
    return redirect('allocation_execution_detail', pk=pk)


# -------------------- Analysis Views --------------------
def allocation_analysis(request):
    days = int(request.GET.get('days', 30))
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')

    start_date = None
    end_date = None
    if start_date_str:
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    if end_date_str:
        from datetime import datetime
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    efficiency = AllocationService.get_allocation_efficiency(days)
    turnover_stats = PredictionStatisticsService.get_inventory_turnover_stats(days)
    allocation_by_granary = PredictionStatisticsService.get_allocation_by_granary(days)

    return render(request, 'allocation/analysis.html', {
        'efficiency': efficiency,
        'turnover_stats': turnover_stats,
        'allocation_by_granary': allocation_by_granary,
        'days': days,
        'start_date': start_date_str,
        'end_date': end_date_str,
    })


# -------------------- Prediction API Views --------------------
def api_prediction_trend(request):
    granary_id = request.GET.get('granary_id', '')
    horizon_days = int(request.GET.get('horizon', 7))
    days = int(request.GET.get('days', 14))
    data = PredictionStatisticsService.get_prediction_trend(granary_id, horizon_days, days)
    return JsonResponse(data, safe=False)


def api_risk_distribution(request):
    horizon_days = int(request.GET.get('horizon', 7))
    data = PredictionStatisticsService.get_risk_distribution(horizon_days)
    return JsonResponse(data)


def api_inventory_distribution(request):
    horizon_days = int(request.GET.get('horizon', 7))
    data = PredictionStatisticsService.get_inventory_distribution(horizon_days)
    return JsonResponse(data)


def api_allocation_efficiency(request):
    days = int(request.GET.get('days', 30))
    data = AllocationService.get_allocation_efficiency(days)
    return JsonResponse(data)


def api_allocation_by_granary(request):
    days = int(request.GET.get('days', 30))
    data = PredictionStatisticsService.get_allocation_by_granary(days)
    return JsonResponse({
        'labels': [d['code'] for d in data],
        'outbound': [round(d['outbound'], 2) for d in data],
        'inbound': [round(d['inbound'], 2) for d in data],
    })


def api_inventory_turnover(request):
    days = int(request.GET.get('days', 30))
    data = PredictionStatisticsService.get_inventory_turnover_stats(days)
    return JsonResponse({
        'labels': [d['code'] for d in data],
        'turnover_days': [d['turnover_days'] for d in data],
        'turnover_rate': [d['turnover_rate'] for d in data],
        'ratios': [d['ratio'] for d in data],
    })
