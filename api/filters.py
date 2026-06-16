import django_filters
from django.db.models import Q
from .models import PaperBatch, StatusChoices, BindingPlan, PlanExecutionStatus, PlanRiskLevel, AnomalyAlert


class PaperBatchFilter(django_filters.FilterSet):
    batch_no = django_filters.CharFilter(lookup_expr='icontains', label='批号(模糊)')
    spec = django_filters.NumberFilter(field_name='spec_id', label='规格ID')
    spec_name = django_filters.CharFilter(field_name='spec__name', lookup_expr='icontains', label='规格名称')
    plate = django_filters.NumberFilter(field_name='plate_id', label='板位ID')
    plate_code = django_filters.CharFilter(field_name='plate__code', lookup_expr='icontains', label='板位编号')
    operator = django_filters.CharFilter(lookup_expr='icontains', label='负责人(模糊)')
    status = django_filters.ChoiceFilter(choices=StatusChoices.choices, label='状态')
    date_from = django_filters.DateFilter(field_name='created_at__date', lookup_expr='gte', label='创建日期起')
    date_to = django_filters.DateFilter(field_name='created_at__date', lookup_expr='lte', label='创建日期止')
    press_date_from = django_filters.DateTimeFilter(field_name='press_start', lookup_expr='gte', label='压平开始起')
    press_date_to = django_filters.DateTimeFilter(field_name='press_start', lookup_expr='lte', label='压平开始止')
    binding_plan = django_filters.NumberFilter(field_name='binding_plan_id', label='装册计划ID')
    has_break = django_filters.BooleanFilter(method='filter_has_break', label='有破口')
    has_warp = django_filters.BooleanFilter(method='filter_has_warp', label='有翘边')
    has_reject = django_filters.BooleanFilter(method='filter_has_reject', label='曾被驳回')

    class Meta:
        model = PaperBatch
        fields = [
            'batch_no', 'spec', 'spec_name', 'plate', 'plate_code',
            'operator', 'status', 'date_from', 'date_to',
            'press_date_from', 'press_date_to', 'binding_plan',
        ]

    def filter_has_break(self, queryset, name, value):
        if value is True:
            return queryset.filter(break_count__gt=0)
        elif value is False:
            return queryset.filter(break_count=0)
        return queryset

    def filter_has_warp(self, queryset, name, value):
        if value is True:
            return queryset.filter(warp_count__gt=0)
        elif value is False:
            return queryset.filter(warp_count=0)
        return queryset

    def filter_has_reject(self, queryset, name, value):
        if value is True:
            return queryset.filter(reject_count__gt=0)
        elif value is False:
            return queryset.filter(reject_count=0)
        return queryset


class BindingPlanFilter(django_filters.FilterSet):
    plan_code = django_filters.CharFilter(lookup_expr='icontains', label='计划号(模糊)')
    operator = django_filters.CharFilter(lookup_expr='icontains', label='负责人(模糊)')
    execution_status = django_filters.ChoiceFilter(choices=PlanExecutionStatus.choices, label='执行状态')
    risk_hint = django_filters.ChoiceFilter(choices=PlanRiskLevel.choices, label='风险提示')
    planned_date_from = django_filters.DateFilter(field_name='planned_date', lookup_expr='gte', label='计划日期起')
    planned_date_to = django_filters.DateFilter(field_name='planned_date', lookup_expr='lte', label='计划日期止')

    class Meta:
        model = BindingPlan
        fields = ['plan_code', 'operator', 'execution_status', 'risk_hint', 'planned_date_from', 'planned_date_to']


class AnomalyAlertFilter(django_filters.FilterSet):
    alert_type = django_filters.ChoiceFilter(choices=AnomalyAlert.ALERT_TYPES, label='异常类型')
    is_resolved = django_filters.BooleanFilter(label='是否已处理')
    batch = django_filters.NumberFilter(field_name='batch_id', label='批次ID')
    binding_plan = django_filters.NumberFilter(method='filter_binding_plan', label='装册计划ID')

    class Meta:
        model = AnomalyAlert
        fields = ['alert_type', 'is_resolved', 'batch', 'binding_plan']

    def filter_binding_plan(self, queryset, name, value):
        return queryset.filter(
            Q(binding_plan_id=value) | Q(batch__binding_plan_id=value)
        ).distinct()
