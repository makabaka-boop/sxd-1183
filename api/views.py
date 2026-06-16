from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Count, Q

from .models import (
    PaperSpec, PressPlate, ReviewRule, BindingPlan,
    PaperBatch, StatusHistory, BreakRecord, AnomalyAlert,
    StatusChoices,
)
from .serializers import (
    PaperSpecSerializer, PressPlateSerializer, ReviewRuleSerializer,
    BindingPlanSerializer, PaperBatchListSerializer, PaperBatchDetailSerializer,
    PaperBatchCreateSerializer, BreakRecordSerializer, StatusHistorySerializer,
    PressStartSerializer, CutResultSerializer, WarpNoteSerializer,
    ReviewSerializer, DetainSerializer, BindConfirmSerializer,
    AnomalyAlertSerializer,
)
from .filters import PaperBatchFilter
from .services import AnomalyDetectionService


class BaseModelViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]


class PaperSpecViewSet(BaseModelViewSet):
    queryset = PaperSpec.objects.all()
    serializer_class = PaperSpecSerializer


class PressPlateViewSet(BaseModelViewSet):
    queryset = PressPlate.objects.all()
    serializer_class = PressPlateSerializer

    @action(detail=True, methods=['get'])
    def current_batches(self, request, pk=None):
        plate = self.get_object()
        batches = PaperBatch.objects.filter(
            plate=plate,
            status__in=[StatusChoices.PRESSING, StatusChoices.PENDING_CUT]
        )
        return Response(PaperBatchListSerializer(batches, many=True).data)

    @action(detail=False, methods=['get'])
    def usage_status(self, request):
        result = []
        for plate in PressPlate.objects.filter(is_active=True):
            active_batches = PaperBatch.objects.filter(
                plate=plate,
                status__in=[StatusChoices.PRESSING, StatusChoices.PENDING_CUT]
            ).count()
            result.append({
                'id': plate.id,
                'code': plate.code,
                'location': plate.location,
                'capacity': plate.capacity,
                'active_count': active_batches,
                'is_available': active_batches == 0,
            })
        return Response(result)


class ReviewRuleViewSet(BaseModelViewSet):
    queryset = ReviewRule.objects.all()
    serializer_class = ReviewRuleSerializer

    @action(detail=False, methods=['get'])
    def active(self, request):
        rule = ReviewRule.get_active()
        if not rule:
            return Response({}, status=404)
        return Response(ReviewRuleSerializer(rule).data)


class BindingPlanViewSet(BaseModelViewSet):
    queryset = BindingPlan.objects.all()
    serializer_class = BindingPlanSerializer

    @action(detail=True, methods=['get'])
    def batches(self, request, pk=None):
        plan = self.get_object()
        batches = PaperBatch.objects.filter(binding_plan=plan)
        return Response(PaperBatchListSerializer(batches, many=True).data)

    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        plan = self.get_object()
        batches = PaperBatch.objects.filter(binding_plan=plan)
        total = batches.count()
        by_status = list(batches.values('status').annotate(count=Count('status')))
        ready_count = batches.filter(status=StatusChoices.READY_BIND).count()
        return Response({
            'plan_code': plan.plan_code,
            'target_quantity': plan.target_quantity,
            'total_batches': total,
            'ready_count': ready_count,
            'completion_rate': (ready_count / total * 100) if total > 0 else 0,
            'by_status': by_status,
        })


class PaperBatchViewSet(BaseModelViewSet):
    queryset = PaperBatch.objects.all()
    filterset_class = PaperBatchFilter
    search_fields = ['batch_no', 'operator', 'plate__code', 'spec__name']
    ordering_fields = [
        'created_at', 'updated_at', 'press_start', 'press_end',
        'batch_no', 'break_count', 'warp_count', 'reject_count',
    ]

    def get_serializer_class(self):
        if self.action == 'create':
            return PaperBatchCreateSerializer
        if self.action == 'retrieve':
            return PaperBatchDetailSerializer
        return PaperBatchListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = PaperBatch.objects.create(**serializer.validated_data)
        StatusHistory.objects.create(
            batch=batch,
            from_status='',
            to_status=StatusChoices.PENDING_PRESS,
            operator=batch.operator,
            remark='创建批次，初始状态',
        )
        headers = self.get_success_headers(serializer.data)
        return Response(
            PaperBatchDetailSerializer(batch).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @action(detail=True, methods=['post'], url_path='press-start')
    def press_start(self, request, pk=None):
        batch = self.get_object()
        serializer = PressStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plate_id = data.get('plate_id')
        if plate_id:
            plate = PressPlate.objects.filter(id=plate_id).first()
            if not plate:
                return Response({'error': '板位不存在'}, status=400)
            AnomalyDetectionService.check_plate_conflict(batch, plate)
            batch.plate = plate
        if not batch.plate:
            return Response({'error': '必须指定压平板位'}, status=400)
        try:
            batch.transition(StatusChoices.PRESSING, operator=data['operator'], remark=data.get('remark', ''))
        except Exception as e:
            return Response({'error': str(e)}, status=400)
        batch.press_start = timezone.now()
        batch.save()
        return Response(PaperBatchDetailSerializer(batch).data)

    @action(detail=True, methods=['post'], url_path='press-finish')
    def press_finish(self, request, pk=None):
        batch = self.get_object()
        operator = request.data.get('operator', batch.operator)
        remark = request.data.get('remark', '')
        try:
            batch.transition(StatusChoices.PENDING_CUT, operator=operator, remark=remark)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
        batch.press_end = timezone.now()
        batch.save()
        return Response(PaperBatchDetailSerializer(batch).data)

    @action(detail=True, methods=['post'], url_path='cut-result')
    def cut_result(self, request, pk=None):
        batch = self.get_object()
        serializer = CutResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if batch.status not in [StatusChoices.PENDING_CUT, StatusChoices.PENDING_REVIEW]:
            return Response({'error': '当前状态不允许提交裁边结果'}, status=400)
        batch.warp_count = data['warp_count']
        batch.warp_note = data.get('warp_note', '')
        batch.break_count = data['break_count']
        batch.break_detail = data.get('break_detail', '')
        batch.save()
        if batch.status == StatusChoices.PENDING_CUT:
            try:
                batch.transition(StatusChoices.PENDING_REVIEW, operator=data['operator'], remark=data.get('remark', ''))
            except Exception as e:
                return Response({'error': str(e)}, status=400)
        AnomalyDetectionService.check_break_cluster(batch)
        return Response(PaperBatchDetailSerializer(batch).data)

    @action(detail=True, methods=['post'], url_path='warp-note')
    def warp_note(self, request, pk=None):
        batch = self.get_object()
        serializer = WarpNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        batch.warp_count = data['warp_count']
        batch.warp_note = data.get('warp_note', '')
        batch.updated_at = timezone.now()
        batch.save()
        return Response(PaperBatchDetailSerializer(batch).data)

    @action(detail=True, methods=['post'], url_path='breaks/add')
    def add_break(self, request, pk=None):
        batch = self.get_object()
        serializer = BreakRecordSerializer(data={**request.data, 'batch': batch.id})
        serializer.is_valid(raise_exception=True)
        br = serializer.save()
        batch.break_count = batch.break_records.count()
        batch.save()
        AnomalyDetectionService.check_break_cluster(batch)
        return Response(BreakRecordSerializer(br).data, status=201)

    @action(detail=True, methods=['get'], url_path='breaks')
    def list_breaks(self, request, pk=None):
        batch = self.get_object()
        return Response(BreakRecordSerializer(batch.break_records.all(), many=True).data)

    @action(detail=True, methods=['post'], url_path='review')
    def review(self, request, pk=None):
        batch = self.get_object()
        if batch.status != StatusChoices.PENDING_REVIEW:
            return Response({'error': '只有待审核状态才能进行审核'}, status=400)
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data['passed']:
            try:
                batch.transition(StatusChoices.READY_BIND, operator=data['operator'], remark=data.get('reason', ''))
            except Exception as e:
                return Response({'error': str(e)}, status=400)
            batch.review_operator = data['operator']
            batch.review_at = timezone.now()
            batch.save()
        else:
            try:
                batch.transition(StatusChoices.PENDING_CUT, operator=data['operator'], remark=data.get('reason', ''))
            except Exception as e:
                return Response({'error': str(e)}, status=400)
            batch.reject_reason = data.get('reason', '审核驳回')
            batch.reject_count += 1
            batch.save()
        return Response(PaperBatchDetailSerializer(batch).data)

    @action(detail=True, methods=['post'], url_path='detain')
    def detain(self, request, pk=None):
        batch = self.get_object()
        serializer = DetainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if batch.status == StatusChoices.DETAINED:
            target = data.get('target_status') or batch.previous_status
            if not target:
                return Response({'error': '解除留置必须指定目标状态'}, status=400)
            try:
                batch.transition(target, operator=data['operator'], remark='解除留置')
            except Exception as e:
                return Response({'error': str(e)}, status=400)
            batch.detain_reason = ''
            batch.detained_at = None
            batch.save()
        else:
            try:
                batch.transition(StatusChoices.DETAINED, operator=data['operator'], remark=data['reason'])
            except Exception as e:
                return Response({'error': str(e)}, status=400)
            batch.detain_reason = data['reason']
            batch.save()
        return Response(PaperBatchDetailSerializer(batch).data)

    @action(detail=True, methods=['post'], url_path='bind-confirm')
    def bind_confirm(self, request, pk=None):
        batch = self.get_object()
        if batch.status != StatusChoices.READY_BIND:
            return Response({'error': '只有可装册状态才能装册确认'}, status=400)
        serializer = BindConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        batch.bind_confirmed_at = timezone.now()
        batch.bind_confirmed_by = data['operator']
        StatusHistory.objects.create(
            batch=batch,
            from_status=batch.status,
            to_status=batch.status,
            operator=data['operator'],
            remark='装册前确认完成',
        )
        batch.save()
        return Response(PaperBatchDetailSerializer(batch).data)

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, pk=None):
        batch = self.get_object()
        return Response(StatusHistorySerializer(batch.status_histories.all(), many=True).data)


class BreakRecordViewSet(BaseModelViewSet):
    queryset = BreakRecord.objects.all()
    serializer_class = BreakRecordSerializer
    filterset_fields = ['batch', 'operator']


class AnomalyAlertViewSet(BaseModelViewSet):
    queryset = AnomalyAlert.objects.all()
    serializer_class = AnomalyAlertSerializer
    filterset_fields = ['alert_type', 'is_resolved', 'batch']

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        alert.is_resolved = True
        alert.save()
        return Response(AnomalyAlertSerializer(alert).data)


class StatsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        AnomalyDetectionService.run_all()
        status_count = list(
            PaperBatch.objects.values('status').annotate(count=Count('status'))
        )
        total = PaperBatch.objects.count()
        pending_review = PaperBatch.objects.filter(status=StatusChoices.PENDING_REVIEW).count()
        pressing = PaperBatch.objects.filter(status=StatusChoices.PRESSING).count()
        return Response({
            'total_batches': total,
            'by_status': status_count,
            'pending_review_count': pending_review,
            'pressing_count': pressing,
            'alert_count': AnomalyAlert.objects.filter(is_resolved=False).count(),
        })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def anomaly_rank(request):
    AnomalyDetectionService.run_all()
    limit = int(request.query_params.get('limit', 20))
    data = AnomalyDetectionService.get_anomaly_batch_rank(limit=limit)
    return Response(data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def pending_review_list(request):
    AnomalyDetectionService.check_review_missing()
    batches = PaperBatch.objects.filter(status=StatusChoices.PENDING_REVIEW).order_by('updated_at')
    filter_backend = PaperBatchFilter(request.GET, queryset=batches)
    page = request.query_params.get('page', None)
    if page:
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 50))
        result_page = paginator.paginate_queryset(filter_backend.qs, request)
        return paginator.get_paginated_response(PaperBatchListSerializer(result_page, many=True).data)
    return Response(PaperBatchListSerializer(filter_backend.qs, many=True).data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def press_duration_distribution(request):
    AnomalyDetectionService.check_press_timeout()
    data = AnomalyDetectionService.get_press_duration_distribution()
    return Response(data)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def run_anomaly_detection(request):
    AnomalyDetectionService.run_all()
    new_alerts = AnomalyAlert.objects.filter(is_resolved=False).count()
    return Response({
        'message': '异常检测已执行',
        'unresolved_alerts': new_alerts,
    })
