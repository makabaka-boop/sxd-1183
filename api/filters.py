import django_filters
from django.db.models import Q, Case, When, IntegerField
from .models import PaperBatch, StatusChoices, BindingPlan, PlanExecutionStatus, PlanRiskLevel, AnomalyAlert, PriorityLevel


class PaperBatchFilter(django_filters.FilterSet):
    batch_no = django_filters.CharFilter(lookup_expr='icontains', label='批号(模糊)')
    spec = django_filters.NumberFilter(field_name='spec_id', label='规格ID')
    spec_name = django_filters.CharFilter(field_name='spec__name', lookup_expr='icontains', label='规格名称')
    plate = django_filters.NumberFilter(field_name='plate_id', label='板位ID')
    plate_code = django_filters.CharFilter(field_name='plate__code', lookup_expr='icontains', label='板位编号')
    operator = django_filters.CharFilter(lookup_expr='icontains', label='负责人(模糊)')
    status = django_filters.ChoiceFilter(choices=StatusChoices.choices, label='状态')
    priority = django_filters.ChoiceFilter(choices=PriorityLevel.choices, label='优先级')
    is_urgent = django_filters.BooleanFilter(label='是否加急')
    date_from = django_filters.DateFilter(field_name='created_at__date', lookup_expr='gte', label='创建日期起')
    date_to = django_filters.DateFilter(field_name='created_at__date', lookup_expr='lte', label='创建日期止')
    press_date_from = django_filters.DateTimeFilter(field_name='press_start', lookup_expr='gte', label='压平开始起')
    press_date_to = django_filters.DateTimeFilter(field_name='press_start', lookup_expr='lte', label='压平开始止')
    binding_plan = django_filters.NumberFilter(field_name='binding_plan_id', label='装册计划ID')
    has_break = django_filters.BooleanFilter(method='filter_has_break', label='有破口')
    has_warp = django_filters.BooleanFilter(method='filter_has_warp', label='有翘边')
    has_reject = django_filters.BooleanFilter(method='filter_has_reject', label='曾被驳回')
    ordering = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('updated_at', 'updated_at'),
            ('press_start', 'press_start'),
            ('press_end', 'press_end'),
            ('batch_no', 'batch_no'),
            ('break_count', 'break_count'),
            ('warp_count', 'warp_count'),
            ('reject_count', 'reject_count'),
            ('is_urgent', 'is_urgent'),
            ('priority_order', 'priority'),
            ('urgent_at', 'urgent_at'),
        ),
        field_labels={
            'is_urgent': '是否加急',
            'priority_order': '优先级',
            'urgent_at': '加急时间',
        }
    )

    class Meta:
        model = PaperBatch
        fields = [
            'batch_no', 'spec', 'spec_name', 'plate', 'plate_code',
            'operator', 'status', 'priority', 'is_urgent',
            'date_from', 'date_to',
            'press_date_from', 'press_date_to', 'binding_plan',
        ]

    def filter_queryset(self, queryset):
        priority_order = Case(
            When(priority=PriorityLevel.EXTREME, then=1),
            When(priority=PriorityLevel.URGENT, then=2),
            When(priority=PriorityLevel.HIGH, then=3),
            When(priority=PriorityLevel.NORMAL, then=4),
            default=5,
            output_field=IntegerField(),
        )
        queryset = queryset.annotate(priority_order=priority_order)
        return super().filter_queryset(queryset)

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
    priority = django_filters.ChoiceFilter(choices=PriorityLevel.choices, label='优先级')
    has_urgent_batches = django_filters.BooleanFilter(method='filter_has_urgent_batches', label='含加急批次')
    planned_date_from = django_filters.DateFilter(field_name='planned_date', lookup_expr='gte', label='计划日期起')
    planned_date_to = django_filters.DateFilter(field_name='planned_date', lookup_expr='lte', label='计划日期止')
    ordering = django_filters.OrderingFilter(
        fields=(
            ('planned_date', 'planned_date'),
            ('created_at', 'created_at'),
            ('plan_code', 'plan_code'),
            ('priority_order', 'priority'),
        ),
        field_labels={
            'priority_order': '优先级',
        }
    )

    class Meta:
        model = BindingPlan
        fields = ['plan_code', 'operator', 'execution_status', 'risk_hint', 'priority', 'planned_date_from', 'planned_date_to']

    def filter_queryset(self, queryset):
        priority_order = Case(
            When(priority=PriorityLevel.EXTREME, then=1),
            When(priority=PriorityLevel.URGENT, then=2),
            When(priority=PriorityLevel.HIGH, then=3),
            When(priority=PriorityLevel.NORMAL, then=4),
            default=5,
            output_field=IntegerField(),
        )
        queryset = queryset.annotate(priority_order=priority_order)
        return super().filter_queryset(queryset)

    def filter_has_urgent_batches(self, queryset, name, value):
        if value is True:
            return queryset.filter(batches__is_urgent=True).distinct()
        elif value is False:
            return queryset.exclude(batches__is_urgent=True).distinct()
        return queryset


class AnomalyAlertFilter(django_filters.FilterSet):
    alert_type = django_filters.ChoiceFilter(choices=AnomalyAlert.ALERT_TYPES, label='异常类型')
    is_resolved = django_filters.BooleanFilter(label='是否已处理')
    batch = django_filters.NumberFilter(field_name='batch_id', label='批次ID')
    binding_plan = django_filters.NumberFilter(method='filter_binding_plan', label='装册计划ID')
    is_urgent_batch = django_filters.BooleanFilter(method='filter_is_urgent_batch', label='加急批次告警')

    class Meta:
        model = AnomalyAlert
        fields = ['alert_type', 'is_resolved', 'batch', 'binding_plan', 'is_urgent_batch']

    def filter_binding_plan(self, queryset, name, value):
        return queryset.filter(
            Q(binding_plan_id=value) | Q(batch__binding_plan_id=value)
        ).distinct()

    def filter_is_urgent_batch(self, queryset, name, value):
        if value is True:
            return queryset.filter(Q(extra__has_key='is_urgent') | Q(batch__is_urgent=True)).distinct()
        elif value is False:
            return queryset.exclude(Q(extra__has_key='is_urgent') | Q(batch__is_urgent=True)).distinct()
        return queryset
