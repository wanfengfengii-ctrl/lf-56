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
    VentilationLog, PestInspection, RiskAssessment
)
from .forms import (
    GrainTypeForm, GranaryForm, TemperatureHumidityLogForm,
    VentilationLogForm, PestInspectionForm, RiskProcessForm
)
from .services import RiskCalculator, recalculate_risks_after_ventilation


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
        messages.success(self.request, '粮仓更新成功')
        return super().form_valid(form)


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
        except Exception:
            pass
        messages.success(self.request, '通风记录添加成功，风险评分已重新计算')
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
        except Exception:
            pass
        messages.success(self.request, '通风记录更新成功，风险评分已重新计算')
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
