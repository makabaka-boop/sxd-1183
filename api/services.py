from django.utils import timezone
from django.db.models import Count, Q
from django.core.exceptions import ValidationError
from .models import (
    PaperBatch, StatusChoices, ReviewRule, AnomalyAlert, PressPlate,
    BindingPlan, PlanExecutionStatus, PlanRiskLevel,
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
                    binding_plan=batch.binding_plan,
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
                        binding_plan=batch.binding_plan,
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
                    binding_plan=batch.binding_plan,
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
                    binding_plan=batch.binding_plan,
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


class PlanExecutionService:

    @classmethod
    def dispatch_plan(cls, plan: BindingPlan) -> BindingPlan:
        if plan.execution_status != PlanExecutionStatus.DRAFT:
            raise ValidationError(f'只有草稿状态的计划才能下发，当前状态：{plan.get_execution_status_display()}')
        plan.execution_status = PlanExecutionStatus.DISPATCHED
        plan.dispatched_at = timezone.now()
        plan.save()
        return plan

    @classmethod
    def add_batches_to_plan(cls, plan: BindingPlan, batch_ids: list) -> dict:
        if plan.execution_status == PlanExecutionStatus.ARCHIVED:
            raise ValidationError('已归档的计划不能添加批次')
        added = []
        skipped = []
        for bid in batch_ids:
            batch = PaperBatch.objects.filter(id=bid).first()
            if not batch:
                skipped.append({'id': bid, 'reason': '批次不存在'})
                continue
            if batch.binding_plan is not None and batch.binding_plan_id != plan.id:
                skipped.append({'id': bid, 'batch_no': batch.batch_no, 'reason': f'批次已关联计划 {batch.binding_plan.plan_code}'})
                continue
            if batch.binding_plan_id == plan.id:
                skipped.append({'id': bid, 'batch_no': batch.batch_no, 'reason': '批次已在本计划中'})
                continue
            batch.binding_plan = plan
            batch.save(update_fields=['binding_plan', 'updated_at'])
            added.append({'id': batch.id, 'batch_no': batch.batch_no})
        cls._update_plan_status_on_batch_change(plan)
        cls._recalculate_risk(plan)
        return {'added': added, 'skipped': skipped}

    @classmethod
    def remove_batches_from_plan(cls, plan: BindingPlan, batch_ids: list) -> dict:
        if plan.execution_status == PlanExecutionStatus.ARCHIVED:
            raise ValidationError('已归档的计划不能移除批次')
        removed = []
        skipped = []
        for bid in batch_ids:
            batch = PaperBatch.objects.filter(id=bid, binding_plan=plan).first()
            if not batch:
                skipped.append({'id': bid, 'reason': '批次不存在或不在本计划中'})
                continue
            if batch.bind_confirmed_at is not None:
                skipped.append({'id': bid, 'batch_no': batch.batch_no, 'reason': '已装册确认的批次不能移除'})
                continue
            batch.binding_plan = None
            batch.save(update_fields=['binding_plan', 'updated_at'])
            removed.append({'id': batch.id, 'batch_no': batch.batch_no})
        cls._update_plan_status_on_batch_change(plan)
        cls._recalculate_risk(plan)
        return {'removed': removed, 'skipped': skipped}

    @classmethod
    def batch_bind_confirm(cls, plan: BindingPlan, batch_ids: list, operator: str) -> dict:
        if plan.execution_status == PlanExecutionStatus.ARCHIVED:
            raise ValidationError('已归档的计划不能进行装册确认')
        confirmed = []
        skipped = []
        for bid in batch_ids:
            batch = PaperBatch.objects.filter(id=bid, binding_plan=plan).first()
            if not batch:
                skipped.append({'id': bid, 'reason': '批次不存在或不在本计划中'})
                continue
            if batch.status != StatusChoices.READY_BIND:
                skipped.append({'id': bid, 'batch_no': batch.batch_no, 'reason': f'批次状态为{batch.get_status_display()}，非可装册状态'})
                continue
            if batch.bind_confirmed_at is not None:
                skipped.append({'id': bid, 'batch_no': batch.batch_no, 'reason': '批次已装册确认'})
                continue
            batch.bind_confirmed_at = timezone.now()
            batch.bind_confirmed_by = operator
            StatusHistory.objects.create(
                batch=batch,
                from_status=batch.status,
                to_status=batch.status,
                operator=operator,
                remark='批量装册确认',
            )
            batch.save()
            confirmed.append({'id': batch.id, 'batch_no': batch.batch_no})
        cls._update_plan_status_on_batch_change(plan)
        cls._recalculate_risk(plan)
        return {'confirmed': confirmed, 'skipped': skipped}

    @classmethod
    def archive_plan(cls, plan: BindingPlan) -> BindingPlan:
        if plan.execution_status != PlanExecutionStatus.COMPLETED:
            raise ValidationError(f'只有已完成状态的计划才能归档，当前状态：{plan.get_execution_status_display()}')
        plan.execution_status = PlanExecutionStatus.ARCHIVED
        plan.archived_at = timezone.now()
        plan.save()
        return plan

    @classmethod
    def recalculate_plan_progress(cls, plan: BindingPlan) -> dict:
        batches = PaperBatch.objects.filter(binding_plan=plan)
        total = batches.count()
        confirmed = batches.filter(bind_confirmed_at__isnull=False).count()
        ready_bind = batches.filter(status=StatusChoices.READY_BIND, bind_confirmed_at__isnull=True).count()
        by_status = list(batches.values('status').annotate(count=Count('status')))
        completion_rate = (confirmed / total * 100) if total > 0 else 0
        total_quantity = sum(b.quantity for b in batches)
        confirmed_quantity = sum(b.quantity for b in batches.filter(bind_confirmed_at__isnull=False))
        return {
            'plan_id': plan.id,
            'plan_code': plan.plan_code,
            'target_quantity': plan.target_quantity,
            'total_batches': total,
            'confirmed_batches': confirmed,
            'ready_bind_batches': ready_bind,
            'completion_rate': round(completion_rate, 2),
            'by_status': by_status,
            'total_quantity': total_quantity,
            'confirmed_quantity': confirmed_quantity,
        }

    @classmethod
    def _update_plan_status_on_batch_change(cls, plan: BindingPlan):
        plan.refresh_from_db()
        batches = PaperBatch.objects.filter(binding_plan=plan)
        total = batches.count()
        if total == 0:
            if plan.execution_status == PlanExecutionStatus.IN_PROGRESS:
                plan.execution_status = PlanExecutionStatus.DISPATCHED
                plan.save(update_fields=['execution_status'])
            return
        confirmed = batches.filter(bind_confirmed_at__isnull=False).count()
        if confirmed == total:
            plan.execution_status = PlanExecutionStatus.COMPLETED
            plan.save(update_fields=['execution_status'])
        elif confirmed > 0 or plan.execution_status in [PlanExecutionStatus.DISPATCHED, PlanExecutionStatus.IN_PROGRESS]:
            if plan.execution_status == PlanExecutionStatus.DRAFT:
                pass
            elif confirmed > 0:
                plan.execution_status = PlanExecutionStatus.IN_PROGRESS
                plan.save(update_fields=['execution_status'])
            elif plan.execution_status == PlanExecutionStatus.DISPATCHED:
                plan.execution_status = PlanExecutionStatus.IN_PROGRESS
                plan.save(update_fields=['execution_status'])

    @classmethod
    def _recalculate_risk(cls, plan: BindingPlan):
        plan.refresh_from_db()
        batches = PaperBatch.objects.filter(binding_plan=plan)
        unresolved_alerts = AnomalyAlert.objects.filter(
            binding_plan=plan, is_resolved=False
        ).count()
        detained_count = batches.filter(status=StatusChoices.DETAINED).count()
        rejected_count = batches.filter(reject_count__gt=0).count()
        score = 0
        score += min(unresolved_alerts * 2, 6)
        score += min(detained_count * 3, 6)
        score += min(rejected_count * 1, 3)
        if score >= 8:
            new_risk = PlanRiskLevel.HIGH
        elif score >= 4:
            new_risk = PlanRiskLevel.MEDIUM
        elif score >= 1:
            new_risk = PlanRiskLevel.LOW
        else:
            new_risk = PlanRiskLevel.NONE
        if plan.risk_hint != new_risk:
            plan.risk_hint = new_risk
            plan.save(update_fields=['risk_hint'])

    @classmethod
    def on_batch_status_changed(cls, batch: PaperBatch):
        if batch.binding_plan:
            cls._update_plan_status_on_batch_change(batch.binding_plan)
            cls._recalculate_risk(batch.binding_plan)

    @classmethod
    def get_plan_dashboard(cls, plan: BindingPlan) -> dict:
        progress = cls.recalculate_plan_progress(plan)
        pending_alerts = AnomalyAlert.objects.filter(
            binding_plan=plan, is_resolved=False
        )
        alert_list = []
        for a in pending_alerts:
            alert_list.append({
                'id': a.id,
                'alert_type': a.alert_type,
                'alert_type_display': a.get_alert_type_display(),
                'message': a.message,
                'batch_no': a.batch.batch_no if a.batch else None,
                'is_resolved': a.is_resolved,
                'created_at': a.created_at,
            })
        progress['pending_alerts'] = alert_list
        progress['pending_alert_count'] = len(alert_list)
        progress['execution_status'] = plan.execution_status
        progress['execution_status_display'] = plan.get_execution_status_display()
        progress['risk_hint'] = plan.risk_hint
        progress['risk_hint_display'] = plan.get_risk_hint_display()
        progress['dispatched_at'] = plan.dispatched_at
        progress['archived_at'] = plan.archived_at
        return progress

    @classmethod
    def get_plan_list_stats(cls) -> list:
        plans = BindingPlan.objects.all()
        result = []
        for plan in plans:
            progress = cls.recalculate_plan_progress(plan)
            pending_alert_count = AnomalyAlert.objects.filter(
                binding_plan=plan, is_resolved=False
            ).count()
            result.append({
                'id': plan.id,
                'plan_code': plan.plan_code,
                'target_quantity': plan.target_quantity,
                'planned_date': plan.planned_date,
                'operator': plan.operator,
                'execution_status': plan.execution_status,
                'execution_status_display': plan.get_execution_status_display(),
                'risk_hint': plan.risk_hint,
                'risk_hint_display': plan.get_risk_hint_display(),
                'total_batches': progress['total_batches'],
                'confirmed_batches': progress['confirmed_batches'],
                'completion_rate': progress['completion_rate'],
                'pending_alert_count': pending_alert_count,
                'dispatched_at': plan.dispatched_at,
                'archived_at': plan.archived_at,
            })
        return result
