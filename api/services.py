from django.utils import timezone
from django.db.models import Count
from .models import (
    PaperBatch, StatusChoices, ReviewRule, AnomalyAlert, PressPlate
)


class AnomalyDetectionService:

    @classmethod
    def check_break_cluster(cls, batch: PaperBatch):
        rule = ReviewRule.get_active()
        if not rule:
            return
        threshold = rule.break_cluster_threshold
        if batch.break_count >= threshold and batch.break_count > 0:
            if not AnomalyAlert.objects.filter(
                batch=batch, alert_type='break_cluster', is_resolved=False
            ).exists():
                AnomalyAlert.objects.create(
                    batch=batch,
                    alert_type='break_cluster',
                    message=f'批号 {batch.batch_no} 破口记录达 {batch.break_count} 处，超过阈值 {threshold}',
                    extra={'break_count': batch.break_count, 'threshold': threshold},
                )

    @classmethod
    def check_press_timeout(cls):
        rule = ReviewRule.get_active()
        if not rule:
            return
        max_minutes = rule.max_press_minutes
        batches = PaperBatch.objects.filter(
            status=StatusChoices.PRESSING,
            press_start__isnull=False,
        )
        for batch in batches:
            if batch.press_duration_minutes > max_minutes:
                if not AnomalyAlert.objects.filter(
                    batch=batch, alert_type='press_timeout', is_resolved=False
                ).exists():
                    AnomalyAlert.objects.create(
                        batch=batch,
                        alert_type='press_timeout',
                        message=f'批号 {batch.batch_no} 压平已 {batch.press_duration_minutes} 分钟，超过阈值 {max_minutes} 分钟',
                        extra={'minutes': batch.press_duration_minutes, 'threshold': max_minutes},
                    )

    @classmethod
    def check_plate_conflict(cls, batch: PaperBatch, plate: PressPlate):
        if not plate:
            return False
        conflict = PaperBatch.objects.filter(
            plate=plate,
            status__in=[StatusChoices.PRESSING, StatusChoices.PENDING_CUT],
        ).exclude(pk=batch.pk).exists()
        if conflict:
            if not AnomalyAlert.objects.filter(
                batch=batch, alert_type='plate_conflict', is_resolved=False
            ).exists():
                AnomalyAlert.objects.create(
                    batch=batch,
                    alert_type='plate_conflict',
                    message=f'板位 {plate.code} 存在冲突，批次 {batch.batch_no} 与其他批次同时占用',
                    extra={'plate_code': plate.code, 'batch_no': batch.batch_no},
                )
        return conflict

    @classmethod
    def check_review_missing(cls):
        rule = ReviewRule.get_active()
        if not rule:
            return
        hours = rule.pending_review_hours
        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        batches = PaperBatch.objects.filter(
            status=StatusChoices.PENDING_REVIEW,
            updated_at__lt=cutoff,
        )
        for batch in batches:
            if not AnomalyAlert.objects.filter(
                batch=batch, alert_type='review_missing', is_resolved=False
            ).exists():
                AnomalyAlert.objects.create(
                    batch=batch,
                    alert_type='review_missing',
                    message=f'批号 {batch.batch_no} 待审核超过 {hours} 小时，审核遗漏风险',
                    extra={'hours': hours, 'pending_since': batch.updated_at.isoformat()},
                )

    @classmethod
    def run_all(cls):
        cls.check_press_timeout()
        cls.check_review_missing()
        batches = PaperBatch.objects.filter(break_count__gt=0)
        for b in batches:
            cls.check_break_cluster(b)

    @classmethod
    def get_anomaly_batch_rank(cls, limit=20):
        alerts = AnomalyAlert.objects.filter(is_resolved=False).values(
            'batch__batch_no'
        ).annotate(
            alert_count=Count('id')
        ).order_by('-alert_count')[:limit]
        result = []
        for item in alerts:
            batch = PaperBatch.objects.filter(batch_no=item['batch__batch_no']).first()
            if batch:
                result.append({
                    'batch_no': item['batch__batch_no'],
                    'spec': str(batch.spec) if batch.spec else '',
                    'status': batch.get_status_display(),
                    'status_code': batch.status,
                    'operator': batch.operator,
                    'alert_count': item['alert_count'],
                })
        return result

    @classmethod
    def get_press_duration_distribution(cls):
        rule = ReviewRule.get_active()
        buckets = [
            {'label': '0-30分钟', 'min': 0, 'max': 30, 'count': 0},
            {'label': '30-60分钟', 'min': 30, 'max': 60, 'count': 0},
            {'label': '60-120分钟', 'min': 60, 'max': 120, 'count': 0},
            {'label': '120分钟以上', 'min': 120, 'max': None, 'count': 0},
        ]
        batches = PaperBatch.objects.filter(press_start__isnull=False)
        for b in batches:
            d = b.press_duration_minutes
            if d == 0:
                continue
            for bucket in buckets:
                if bucket['max'] is None:
                    if d >= bucket['min']:
                        bucket['count'] += 1
                        break
                elif bucket['min'] <= d < bucket['max']:
                    bucket['count'] += 1
                    break
        if rule:
            timeout_batches = PaperBatch.objects.filter(
                press_start__isnull=False
            ).extra(where=[
                "(CASE WHEN press_end IS NOT NULL THEN (julianday(press_end) - julianday(press_start))*1440 ELSE (julianday('now') - julianday(press_start))*1440 END) >= %s"
            ], params=[rule.max_press_minutes]).count()
        else:
            timeout_batches = 0
        return {
            'buckets': buckets,
            'total_completed_with_press': batches.filter(press_end__isnull=False).count(),
            'timeout_count': timeout_batches,
        }
