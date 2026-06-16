from rest_framework import serializers
from .models import (
    PaperSpec, PressPlate, ReviewRule, BindingPlan,
    PaperBatch, StatusHistory, BreakRecord, AnomalyAlert,
    StatusChoices, PlanExecutionStatus, PlanRiskLevel, PriorityLevel,
)


class PaperSpecSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaperSpec
        fields = '__all__'


class PressPlateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PressPlate
        fields = '__all__'


class ReviewRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewRule
        fields = '__all__'


class BreakRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BreakRecord
        fields = '__all__'


class StatusHistorySerializer(serializers.ModelSerializer):
    from_status_display = serializers.CharField(source='get_from_status_display', read_only=True)
    to_status_display = serializers.CharField(source='get_to_status_display', read_only=True)

    class Meta:
        model = StatusHistory
        fields = '__all__'


class PaperBatchListSerializer(serializers.ModelSerializer):
    spec_name = serializers.CharField(source='spec.name', read_only=True)
    spec_detail = serializers.CharField(source='spec.__str__', read_only=True)
    plate_code = serializers.CharField(source='plate.code', read_only=True, default=None)
    binding_plan_code = serializers.CharField(source='binding_plan.plan_code', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    press_duration_minutes = serializers.IntegerField(read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    class Meta:
        model = PaperBatch
        fields = [
            'id', 'batch_no', 'spec', 'spec_name', 'spec_detail',
            'quantity', 'plate', 'plate_code', 'binding_plan', 'binding_plan_code',
            'status', 'status_display', 'operator',
            'press_start', 'press_end', 'press_duration_minutes',
            'warp_count', 'break_count', 'reject_count',
            'detain_reason', 'reject_reason',
            'review_operator', 'review_at',
            'bind_confirmed_at', 'bind_confirmed_by',
            'priority', 'priority_display', 'is_urgent', 'urgent_reason',
            'urgent_at', 'urgent_operator',
            'created_at', 'updated_at',
        ]


class PaperBatchDetailSerializer(serializers.ModelSerializer):
    spec_name = serializers.CharField(source='spec.name', read_only=True)
    spec_detail = serializers.CharField(source='spec.__str__', read_only=True)
    plate_code = serializers.CharField(source='plate.code', read_only=True, default=None)
    binding_plan_code = serializers.CharField(source='binding_plan.plan_code', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    press_duration_minutes = serializers.IntegerField(read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    break_records = BreakRecordSerializer(many=True, read_only=True)
    status_histories = StatusHistorySerializer(many=True, read_only=True)
    allowed_transitions = serializers.SerializerMethodField()

    class Meta:
        model = PaperBatch
        fields = '__all__'
        read_only_fields = ['status', 'press_start', 'press_end', 'created_at', 'updated_at', 'is_urgent', 'urgent_at', 'urgent_operator', 'urgent_cancel_at', 'urgent_cancel_operator']

    def get_allowed_transitions(self, obj):
        from .models import TRANSITIONS
        allowed = TRANSITIONS.get(obj.status, [])
        return [
            {'code': s, 'display': dict(StatusChoices.choices).get(s, s)}
            for s in allowed
        ]


class PaperBatchCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaperBatch
        fields = [
            'batch_no', 'spec', 'quantity', 'plate',
            'binding_plan', 'operator', 'priority', 'urgent_reason',
        ]

    def validate(self, attrs):
        plate = attrs.get('plate')
        if plate:
            from .services import AnomalyDetectionService
            temp_batch = PaperBatch(plate=plate)
            if AnomalyDetectionService.check_plate_conflict(temp_batch, plate):
                raise serializers.ValidationError({'plate': f'板位 {plate.code} 已被其他批次占用，存在冲突'})
        return attrs


class BindingPlanListSerializer(serializers.ModelSerializer):
    execution_status_display = serializers.CharField(source='get_execution_status_display', read_only=True)
    risk_hint_display = serializers.CharField(source='get_risk_hint_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    total_batches = serializers.IntegerField(read_only=True, default=0)
    confirmed_batches = serializers.IntegerField(read_only=True, default=0)
    completion_rate = serializers.FloatField(read_only=True, default=0)
    pending_alert_count = serializers.IntegerField(read_only=True, default=0)
    urgent_batch_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = BindingPlan
        fields = [
            'id', 'plan_code', 'target_quantity', 'planned_date', 'operator',
            'remark', 'priority', 'priority_display', 'urgent_reason',
            'execution_status', 'execution_status_display',
            'risk_hint', 'risk_hint_display',
            'dispatched_at', 'archived_at', 'created_at',
            'total_batches', 'confirmed_batches', 'completion_rate',
            'pending_alert_count', 'urgent_batch_count',
        ]


class BindingPlanDetailSerializer(serializers.ModelSerializer):
    execution_status_display = serializers.CharField(source='get_execution_status_display', read_only=True)
    risk_hint_display = serializers.CharField(source='get_risk_hint_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    batches = PaperBatchListSerializer(many=True, read_only=True)

    class Meta:
        model = BindingPlan
        fields = '__all__'
        read_only_fields = ['execution_status', 'risk_hint', 'dispatched_at', 'archived_at', 'created_at']


class BindingPlanDashboardSerializer(serializers.Serializer):
    pass


class BatchIdsSerializer(serializers.Serializer):
    batch_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False
    )


class BatchBindConfirmActionSerializer(serializers.Serializer):
    batch_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False
    )
    operator = serializers.CharField(max_length=50)


class PressStartSerializer(serializers.Serializer):
    operator = serializers.CharField(max_length=50)
    plate_id = serializers.IntegerField(required=False, allow_null=True)
    remark = serializers.CharField(max_length=500, required=False, allow_blank=True)


class CutResultSerializer(serializers.Serializer):
    operator = serializers.CharField(max_length=50)
    warp_count = serializers.IntegerField(default=0, min_value=0)
    warp_note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    break_count = serializers.IntegerField(default=0, min_value=0)
    break_detail = serializers.CharField(max_length=500, required=False, allow_blank=True)
    remark = serializers.CharField(max_length=500, required=False, allow_blank=True)


class WarpNoteSerializer(serializers.Serializer):
    operator = serializers.CharField(max_length=50)
    warp_count = serializers.IntegerField(min_value=0)
    warp_note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ReviewSerializer(serializers.Serializer):
    operator = serializers.CharField(max_length=50)
    passed = serializers.BooleanField()
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class DetainSerializer(serializers.Serializer):
    operator = serializers.CharField(max_length=50)
    reason = serializers.CharField(max_length=500)
    target_status = serializers.ChoiceField(choices=StatusChoices.choices, required=False, allow_null=True)


class BindConfirmSerializer(serializers.Serializer):
    operator = serializers.CharField(max_length=50)


class BatchUrgentSerializer(serializers.Serializer):
    operator = serializers.CharField(max_length=50)
    urgent_reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=PriorityLevel.choices, required=False, default=PriorityLevel.URGENT)


class BatchCancelUrgentSerializer(serializers.Serializer):
    operator = serializers.CharField(max_length=50)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class BatchPriorityUpdateSerializer(serializers.Serializer):
    operator = serializers.CharField(max_length=50)
    priority = serializers.ChoiceField(choices=PriorityLevel.choices)


class AnomalyAlertSerializer(serializers.ModelSerializer):
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    batch_no = serializers.CharField(source='batch.batch_no', read_only=True, default=None)
    binding_plan_code = serializers.CharField(source='binding_plan.plan_code', read_only=True, default=None)

    class Meta:
        model = AnomalyAlert
        fields = '__all__'
