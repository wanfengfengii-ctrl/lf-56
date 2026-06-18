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
    AllocationExecution, GrainSituationPrediction,
    Region, TransportRoute, AllocationBatch, ExecutionNode,
    AbnormalLoss, ArrivalVerification
)
from .forms import (
    GrainTypeForm, GranaryForm, TemperatureHumidityLogForm,
    VentilationLogForm, PestInspectionForm, RiskProcessForm,
    WarningCreateForm, DisposalTaskAssignForm, DisposalProgressForm,
    DisposalSubmitForm, DisposalReviewForm, DisposalArchiveForm, WarningFilterForm,
    InventoryChangeLogForm, AllocationConfigForm, AllocationSuggestionForm,
    AllocationSuggestionApproveForm, AllocationExecutionForm,
    PredictionGenerateForm, AllocationGenerateForm,
    RegionForm, TransportRouteForm, AllocationBatchForm,
    BatchSplitForm, BatchMergeForm, ExecutionNodeForm,
    NodeCompleteForm, AbnormalLossForm, LossHandleForm,
    ArrivalVerificationForm, VerificationConfirmForm, GranaryRegionForm
)
from .services import (
    RiskCalculator, recalculate_risks_after_ventilation, recalculate_risks_for_granary,
    WarningService, DisposalService, WarningStatisticsService,
    GrainSituationPredictionService, InventoryService, AllocationService,
    PredictionStatisticsService,
    BatchService, NodeTrackingService, LossService,
    ArrivalVerificationService, CollaborativeAnalyticsService
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
    execution = get_object_or_404(AllocationExecution.objects.select_related(
        'suggestion__source_granary', 'suggestion__target_granary'
    ), pk=pk)
    batches = execution.batches.select_related('route').order_by('-created_at')
    batch_form = AllocationBatchForm(execution=execution)
    merge_form = BatchMergeForm()
    form = AllocationExecutionForm(instance=execution)
    return render(request, 'allocation/execution_detail.html', {
        'execution': execution,
        'form': form,
        'batches': batches,
        'batch_form': batch_form,
        'merge_form': merge_form,
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


def api_allocation_trend(request):
    period = int(request.GET.get('period', 30))
    from django.utils import timezone
    from datetime import timedelta
    end_date = timezone.now()
    start_date = end_date - timedelta(days=period)
    executions = AllocationExecution.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
    date_map = {}
    for ex in executions:
        d = ex.created_at.strftime('%Y-%m-%d')
        if d not in date_map:
            date_map[d] = {'count': 0, 'quantity': 0.0}
        date_map[d]['count'] += 1
        date_map[d]['quantity'] += ex.actual_quantity or ex.suggestion.suggested_quantity
    sorted_dates = sorted(date_map.keys())
    return JsonResponse({
        'labels': sorted_dates,
        'quantities': [round(date_map[d]['quantity'], 2) for d in sorted_dates],
        'counts': [date_map[d]['count'] for d in sorted_dates],
    })


def api_allocation_status(request):
    period = int(request.GET.get('period', 30))
    from django.utils import timezone
    from datetime import timedelta
    start_date = timezone.now() - timedelta(days=period)
    suggestions = AllocationSuggestion.objects.filter(created_at__gte=start_date)
    status_counts = {}
    for s in suggestions:
        label = s.get_status_display()
        status_counts[label] = status_counts.get(label, 0) + 1
    return JsonResponse({
        'labels': list(status_counts.keys()),
        'data': list(status_counts.values()),
    })


def api_turnover_trend(request):
    period = int(request.GET.get('period', 30))
    data = PredictionStatisticsService.get_inventory_turnover_stats(period)
    return JsonResponse({
        'labels': [d['code'] for d in data],
        'rates': [round(d['turnover_rate'], 2) for d in data],
    })


def api_granary_turnover(request):
    period = int(request.GET.get('period', 30))
    data = PredictionStatisticsService.get_allocation_by_granary(period)
    return JsonResponse({
        'labels': [d['code'] for d in data],
        'in_quantities': [round(d.get('inbound', 0), 2) for d in data],
        'out_quantities': [round(d.get('outbound', 0), 2) for d in data],
    })


def api_risk_reduction(request):
    period = int(request.GET.get('period', 30))
    from django.utils import timezone
    from datetime import timedelta
    end_date = timezone.now()
    start_date = end_date - timedelta(days=period)
    granaries = Granary.objects.all()
    labels = []
    risk_scores = []
    reductions = []
    for g in granaries:
        latest_risk = RiskAssessment.objects.filter(granary=g).order_by('-assessment_date').first()
        prev_risk = RiskAssessment.objects.filter(granary=g, assessment_date__lt=start_date).order_by('-assessment_date').first()
        labels.append(g.code)
        current_score = latest_risk.overall_risk if latest_risk else 0
        risk_scores.append(round(current_score, 2))
        if prev_risk and prev_risk.overall_risk > 0:
            reduction = round((prev_risk.overall_risk - current_score) / prev_risk.overall_risk * 100, 1)
        else:
            reduction = 0
        reductions.append(reduction)
    return JsonResponse({
        'labels': labels,
        'risk_scores': risk_scores,
        'reductions': reductions,
    })


def api_allocation_cost(request):
    period = int(request.GET.get('period', 30))
    from django.utils import timezone
    from datetime import timedelta
    start_date = timezone.now() - timedelta(days=period)
    suggestions = AllocationSuggestion.objects.filter(created_at__gte=start_date)
    date_map = {}
    for s in suggestions:
        d = s.created_at.strftime('%Y-%m-%d')
        date_map[d] = date_map.get(d, 0) + s.suggested_quantity * 10
    sorted_dates = sorted(date_map.keys())
    return JsonResponse({
        'labels': sorted_dates,
        'costs': [round(date_map[d], 2) for d in sorted_dates],
    })


# -------------------- Region Views --------------------
class RegionListView(ListView):
    model = Region
    template_name = 'region/list.html'
    context_object_name = 'regions'
    ordering = ['code']


class RegionCreateView(CreateView):
    model = Region
    form_class = RegionForm
    template_name = 'region/form.html'
    success_url = reverse_lazy('region_list')

    def form_valid(self, form):
        messages.success(self.request, '区域创建成功')
        return super().form_valid(form)


class RegionUpdateView(UpdateView):
    model = Region
    form_class = RegionForm
    template_name = 'region/form.html'
    success_url = reverse_lazy('region_list')

    def form_valid(self, form):
        messages.success(self.request, '区域更新成功')
        return super().form_valid(form)


class RegionDeleteView(DeleteView):
    model = Region
    template_name = 'region/confirm_delete.html'
    success_url = reverse_lazy('region_list')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.granaries.exists() or obj.children.exists():
            messages.error(request, '该区域下有粮仓或子区域，无法删除')
            return redirect(self.success_url)
        messages.success(request, '区域删除成功')
        return super().delete(request, *args, **kwargs)


# -------------------- Transport Route Views --------------------
class TransportRouteListView(ListView):
    model = TransportRoute
    template_name = 'transport_route/list.html'
    context_object_name = 'routes'
    ordering = ['source_granary__code']
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related('source_granary', 'target_granary')
        source_id = self.request.GET.get('source')
        target_id = self.request.GET.get('target')
        if source_id:
            qs = qs.filter(source_granary_id=source_id)
        if target_id:
            qs = qs.filter(target_granary_id=target_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['granaries'] = Granary.objects.filter(is_active=True)
        ctx['selected_source'] = self.request.GET.get('source', '')
        ctx['selected_target'] = self.request.GET.get('target', '')
        return ctx


class TransportRouteCreateView(CreateView):
    model = TransportRoute
    form_class = TransportRouteForm
    template_name = 'transport_route/form.html'
    success_url = reverse_lazy('transport_route_list')

    def form_valid(self, form):
        messages.success(self.request, '运输路径创建成功')
        return super().form_valid(form)


class TransportRouteUpdateView(UpdateView):
    model = TransportRoute
    form_class = TransportRouteForm
    template_name = 'transport_route/form.html'
    success_url = reverse_lazy('transport_route_list')

    def form_valid(self, form):
        messages.success(self.request, '运输路径更新成功')
        return super().form_valid(form)


class TransportRouteDeleteView(DeleteView):
    model = TransportRoute
    template_name = 'transport_route/confirm_delete.html'
    success_url = reverse_lazy('transport_route_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, '运输路径删除成功')
        return super().delete(request, *args, **kwargs)


# -------------------- Batch Views --------------------
def batch_list(request):
    status = request.GET.get('status', '')
    execution_id = request.GET.get('execution', '')
    queryset = AllocationBatch.objects.select_related(
        'execution', 'execution__suggestion__source_granary',
        'execution__suggestion__target_granary', 'route'
    ).order_by('-created_at')

    if status:
        queryset = queryset.filter(status=status)
    if execution_id:
        queryset = queryset.filter(execution_id=execution_id)

    return render(request, 'batch/list.html', {
        'batches': queryset[:100],
        'selected_status': status,
        'selected_execution': execution_id,
    })


def batch_detail(request, pk):
    batch = get_object_or_404(AllocationBatch.objects.select_related(
        'execution__suggestion__source_granary',
        'execution__suggestion__target_granary',
        'route'
    ), pk=pk)
    nodes = batch.nodes.all().order_by('node_order')
    losses = batch.abnormal_losses.all().order_by('-created_at')
    verification = getattr(batch, 'arrival_verification', None)

    batch_form = AllocationBatchForm(instance=batch, execution=batch.execution)
    split_form = BatchSplitForm()
    node_form = ExecutionNodeForm()
    node_complete_form = NodeCompleteForm()
    loss_form = AbnormalLossForm()
    loss_handle_form = LossHandleForm()
    verification_form = ArrivalVerificationForm(instance=verification) if verification else None
    verification_create_form = ArrivalVerificationForm()
    confirm_form = VerificationConfirmForm()

    return render(request, 'batch/detail.html', {
        'batch': batch,
        'nodes': nodes,
        'losses': losses,
        'verification': verification,
        'batch_form': batch_form,
        'split_form': split_form,
        'node_form': node_form,
        'node_complete_form': node_complete_form,
        'loss_form': loss_form,
        'loss_handle_form': loss_handle_form,
        'verification_form': verification_form,
        'verification_create_form': verification_create_form,
        'confirm_form': confirm_form,
    })


def batch_update(request, pk):
    batch = get_object_or_404(AllocationBatch, pk=pk)
    if request.method == 'POST':
        form = AllocationBatchForm(request.POST, instance=batch, execution=batch.execution)
        if form.is_valid():
            form.save()
            messages.success(request, '批次信息已更新')
            return redirect('batch_detail', pk=pk)
    return redirect('batch_detail', pk=pk)


def batch_update_status(request, pk):
    batch = get_object_or_404(AllocationBatch, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status')
        operator = request.POST.get('operator', '系统')
        try:
            BatchService.update_batch_status(batch, status=status, operator=operator)
            if status == 'in_transit' and not batch.nodes.exists():
                NodeTrackingService.create_default_nodes(batch)
            messages.success(request, f'状态已更新为：{batch.get_status_display()}')
        except Exception as e:
            messages.error(request, f'状态更新失败：{str(e)}')
    return redirect('batch_detail', pk=pk)


def batch_split(request, pk):
    batch = get_object_or_404(AllocationBatch, pk=pk)
    if request.method == 'POST':
        form = BatchSplitForm(request.POST)
        if form.is_valid():
            try:
                child_batches = BatchService.split_batch(
                    batch,
                    split_quantities=form.cleaned_data['quantities'],
                    operator=form.cleaned_data.get('operator'),
                )
                for child in child_batches:
                    NodeTrackingService.create_default_nodes(child)
                messages.success(request, f'批次已拆分为{len(child_batches)}个子批次')
                return redirect('allocation_execution_detail', pk=batch.execution_id)
            except ValueError as e:
                messages.error(request, str(e))
    return redirect('batch_detail', pk=pk)


def batch_merge(request, execution_pk):
    execution = get_object_or_404(AllocationExecution, pk=execution_pk)
    if request.method == 'POST':
        form = BatchMergeForm(request.POST)
        if form.is_valid():
            batch_ids_str = form.cleaned_data.get('batch_ids', '')
            batch_ids = [int(x) for x in batch_ids_str.split(',') if x.strip()]
            batches = AllocationBatch.objects.filter(
                pk__in=batch_ids, execution_id=execution_pk
            )
            try:
                merged = BatchService.merge_batches(
                    list(batches),
                    operator=form.cleaned_data.get('operator'),
                )
                NodeTrackingService.create_default_nodes(merged)
                messages.success(request, f'已合并为批次：{merged.batch_no}')
            except ValueError as e:
                messages.error(request, str(e))
    return redirect('allocation_execution_detail', pk=execution_pk)


def batch_create(request, execution_pk):
    execution = get_object_or_404(AllocationExecution, pk=execution_pk)
    if request.method == 'POST':
        form = AllocationBatchForm(request.POST, execution=execution)
        if form.is_valid():
            try:
                batch = BatchService.create_batch(
                    execution=execution,
                    quantity=form.cleaned_data['quantity'],
                    route=form.cleaned_data.get('route'),
                    operator=form.cleaned_data.get('operator'),
                    estimated_departure=form.cleaned_data.get('estimated_departure'),
                    estimated_arrival=form.cleaned_data.get('estimated_arrival'),
                    transporter=form.cleaned_data.get('transporter'),
                    vehicle_no=form.cleaned_data.get('vehicle_no'),
                    driver=form.cleaned_data.get('driver'),
                    driver_phone=form.cleaned_data.get('driver_phone'),
                    remark=form.cleaned_data.get('remark'),
                )
                NodeTrackingService.create_default_nodes(batch)
                messages.success(request, f'批次创建成功：{batch.batch_no}')
                return redirect('batch_detail', pk=batch.pk)
            except ValueError as e:
                messages.error(request, str(e))
    return redirect('allocation_execution_detail', pk=execution_pk)


# -------------------- Execution Node Views --------------------
def node_create(request, batch_pk):
    batch = get_object_or_404(AllocationBatch, pk=batch_pk)
    if request.method == 'POST':
        form = ExecutionNodeForm(request.POST)
        if form.is_valid():
            node = NodeTrackingService.create_node(
                batch=batch,
                node_type=form.cleaned_data['node_type'],
                node_name=form.cleaned_data['node_name'],
                node_order=form.cleaned_data.get('node_order', 0),
                location=form.cleaned_data.get('location'),
                granary=form.cleaned_data.get('granary'),
                planned_time=form.cleaned_data.get('planned_time'),
                remark=form.cleaned_data.get('remark'),
            )
            messages.success(request, f'节点创建成功：{node.node_name}')
    return redirect('batch_detail', pk=batch_pk)


def node_complete(request, pk):
    node = get_object_or_404(ExecutionNode, pk=pk)
    if request.method == 'POST':
        form = NodeCompleteForm(request.POST)
        if form.is_valid():
            NodeTrackingService.complete_node(
                node=node,
                operator=form.cleaned_data.get('operator'),
                quantity_checked=form.cleaned_data.get('quantity_checked'),
                temperature=form.cleaned_data.get('temperature'),
                humidity=form.cleaned_data.get('humidity'),
                remark=form.cleaned_data.get('remark'),
            )
            messages.success(request, f'节点"{node.node_name}"已完成')
    return redirect('batch_detail', pk=node.batch_id)


def node_depart(request, pk):
    node = get_object_or_404(ExecutionNode, pk=pk)
    if request.method == 'POST':
        operator = request.POST.get('operator', '系统')
        NodeTrackingService.depart_node(node, operator=operator)
        messages.success(request, f'已从节点"{node.node_name}"出发')
    return redirect('batch_detail', pk=node.batch_id)


def node_delete(request, pk):
    node = get_object_or_404(ExecutionNode, pk=pk)
    batch_id = node.batch_id
    node.delete()
    messages.success(request, '节点已删除')
    return redirect('batch_detail', pk=batch_id)


# -------------------- Abnormal Loss Views --------------------
def loss_list(request):
    status = request.GET.get('status', '')
    loss_type = request.GET.get('loss_type', '')
    queryset = AbnormalLoss.objects.select_related(
        'batch', 'batch__execution__suggestion__source_granary',
        'batch__execution__suggestion__target_granary', 'node'
    ).order_by('-created_at')

    if status:
        queryset = queryset.filter(status=status)
    if loss_type:
        queryset = queryset.filter(loss_type=loss_type)

    return render(request, 'loss/list.html', {
        'losses': queryset[:100],
        'selected_status': status,
        'selected_type': loss_type,
    })


def loss_create(request, batch_pk):
    batch = get_object_or_404(AllocationBatch, pk=batch_pk)
    if request.method == 'POST':
        form = AbnormalLossForm(request.POST)
        if form.is_valid():
            loss = LossService.report_loss(
                batch=batch,
                loss_type=form.cleaned_data['loss_type'],
                loss_quantity=form.cleaned_data['loss_quantity'],
                description=form.cleaned_data['description'],
                discovered_by=form.cleaned_data.get('discovered_by'),
                severity=form.cleaned_data.get('severity', 'moderate'),
                estimated_cost=form.cleaned_data.get('estimated_cost', 0),
                discovered_location=form.cleaned_data.get('discovered_location'),
            )
            messages.success(request, f'损耗已登记：{loss.get_loss_type_display()} {loss.loss_quantity}吨')
    return redirect('batch_detail', pk=batch_pk)


def loss_handle(request, pk):
    loss = get_object_or_404(AbnormalLoss, pk=pk)
    if request.method == 'POST':
        form = LossHandleForm(request.POST)
        if form.is_valid():
            action = request.POST.get('action', 'investigate')
            data = form.cleaned_data
            try:
                if action == 'investigate':
                    LossService.investigate_loss(
                        loss,
                        cause_analysis=data.get('cause_analysis', ''),
                        handled_by=data.get('handled_by'),
                    )
                    messages.success(request, '已进入调查阶段')
                elif action == 'resolve':
                    LossService.resolve_loss(
                        loss,
                        handling_measures=data.get('handling_measures', ''),
                        handled_by=data.get('handled_by'),
                    )
                    messages.success(request, '已完成处置')
                elif action == 'confirm':
                    LossService.confirm_loss(
                        loss,
                        actual_cost=data.get('actual_cost'),
                        confirmed_by=data.get('confirmed_by'),
                        handling_result=data.get('handling_result'),
                    )
                    messages.success(request, '已确认损失')
                elif action == 'close':
                    LossService.close_loss(loss, remark=data.get('remark'))
                    messages.success(request, '已归档关闭')
            except Exception as e:
                messages.error(request, str(e))
    return redirect('batch_detail', pk=loss.batch_id)


# -------------------- Arrival Verification Views --------------------
def verification_list(request):
    status = request.GET.get('status', '')
    queryset = ArrivalVerification.objects.select_related(
        'batch', 'batch__execution__suggestion__source_granary',
        'batch__execution__suggestion__target_granary'
    ).order_by('-created_at')

    if status:
        queryset = queryset.filter(status=status)

    return render(request, 'verification/list.html', {
        'verifications': queryset[:100],
        'selected_status': status,
    })


def verification_create(request, batch_pk):
    batch = get_object_or_404(AllocationBatch, pk=batch_pk)
    if request.method == 'POST':
        form = ArrivalVerificationForm(request.POST)
        if form.is_valid():
            try:
                verification = ArrivalVerificationService.create_verification(
                    batch=batch,
                    actual_received=form.cleaned_data.get('actual_received'),
                )
                messages.success(request, f'到仓复核已创建：{verification.verification_no}')
                return redirect('verification_detail', pk=verification.pk)
            except ValueError as e:
                messages.error(request, str(e))
    return redirect('batch_detail', pk=batch_pk)


def verification_detail(request, pk):
    verification = get_object_or_404(ArrivalVerification.objects.select_related(
        'batch', 'batch__execution__suggestion__source_granary',
        'batch__execution__suggestion__target_granary'
    ), pk=pk)
    form = ArrivalVerificationForm(instance=verification)
    confirm_form = VerificationConfirmForm()
    return render(request, 'verification/detail.html', {
        'verification': verification,
        'form': form,
        'confirm_form': confirm_form,
    })


def verification_submit(request, pk):
    verification = get_object_or_404(ArrivalVerification, pk=pk)
    if request.method == 'POST':
        form = ArrivalVerificationForm(request.POST, instance=verification)
        if form.is_valid():
            ArrivalVerificationService.verify(
                verification=verification,
                actual_received=form.cleaned_data['actual_received'],
                quality_check_passed=form.cleaned_data.get('quality_check_passed', True),
                verifier=form.cleaned_data.get('verifier'),
                quality_report=form.cleaned_data.get('quality_report'),
                moisture_content=form.cleaned_data.get('moisture_content'),
                impurity_rate=form.cleaned_data.get('impurity_rate'),
                temperature=form.cleaned_data.get('temperature'),
                discrepancy_description=form.cleaned_data.get('discrepancy_description'),
                handling_suggestion=form.cleaned_data.get('handling_suggestion'),
                remark=form.cleaned_data.get('remark'),
            )
            messages.success(request, f'复核完成，状态：{verification.get_status_display()}')
            return redirect('verification_detail', pk=pk)
    return redirect('verification_detail', pk=pk)


def verification_confirm(request, pk):
    verification = get_object_or_404(ArrivalVerification, pk=pk)
    if request.method == 'POST':
        form = VerificationConfirmForm(request.POST)
        if form.is_valid():
            ArrivalVerificationService.confirm_verification(
                verification=verification,
                confirmed_by=form.cleaned_data['confirmed_by'],
                handling_suggestion=form.cleaned_data.get('handling_suggestion'),
            )
            messages.success(request, '复核结果已确认')
    return redirect('verification_detail', pk=pk)


# -------------------- Collaborative Analytics Views --------------------
def collaborative_dashboard(request):
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

    timeliness = CollaborativeAnalyticsService.get_timeliness_stats(days, start_date, end_date)
    loss_stats = CollaborativeAnalyticsService.get_loss_rate_stats(days, start_date, end_date)
    execution_stats = CollaborativeAnalyticsService.get_execution_rate_stats(days, start_date, end_date)
    efficiency = CollaborativeAnalyticsService.get_collaboration_efficiency(days, start_date, end_date)
    region_stats = CollaborativeAnalyticsService.get_region_collaboration_stats(days)
    route_stats = CollaborativeAnalyticsService.get_transport_route_stats(days)

    return render(request, 'allocation/collaborative_dashboard.html', {
        'timeliness': timeliness,
        'loss_stats': loss_stats,
        'execution_stats': execution_stats,
        'efficiency': efficiency,
        'region_stats': region_stats,
        'route_stats': route_stats,
        'days': days,
        'start_date': start_date_str,
        'end_date': end_date_str,
    })


# -------------------- Collaborative Analytics API Views --------------------
def api_timeliness_stats(request):
    days = int(request.GET.get('days', 30))
    data = CollaborativeAnalyticsService.get_timeliness_stats(days)
    return JsonResponse(data)


def api_loss_rate_stats(request):
    days = int(request.GET.get('days', 30))
    data = CollaborativeAnalyticsService.get_loss_rate_stats(days)
    return JsonResponse(data)


def api_execution_rate_stats(request):
    days = int(request.GET.get('days', 30))
    data = CollaborativeAnalyticsService.get_execution_rate_stats(days)
    return JsonResponse(data)


def api_collaboration_efficiency(request):
    days = int(request.GET.get('days', 30))
    data = CollaborativeAnalyticsService.get_collaboration_efficiency(days)
    return JsonResponse(data)


def api_region_collaboration(request):
    days = int(request.GET.get('days', 30))
    data = CollaborativeAnalyticsService.get_region_collaboration_stats(days)
    return JsonResponse({
        'labels': [f"{d['source_region']}→{d['target_region']}" for d in data],
        'counts': [d['count'] for d in data],
        'quantities': [d['quantity'] for d in data],
    })


def api_route_efficiency(request):
    days = int(request.GET.get('days', 30))
    data = CollaborativeAnalyticsService.get_transport_route_stats(days)
    return JsonResponse({
        'labels': [d['route'] for d in data],
        'counts': [d['count'] for d in data],
        'efficiency_rates': [d['efficiency_rate'] for d in data],
        'estimated_hours': [d['estimated_hours'] for d in data],
        'actual_hours': [d['avg_actual_hours'] for d in data],
    })


def api_loss_by_type(request):
    days = int(request.GET.get('days', 30))
    data = CollaborativeAnalyticsService.get_loss_rate_stats(days)
    loss_by_type = data.get('loss_by_type', {})
    return JsonResponse({
        'labels': list(loss_by_type.keys()),
        'quantities': [round(v, 2) for v in loss_by_type.values()],
    })
