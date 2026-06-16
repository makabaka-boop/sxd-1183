from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class StatusChoices(models.TextChoices):
    PENDING_PRESS = 'pending_press', '待压平'
    PRESSING = 'pressing', '压平中'
    PENDING_CUT = 'pending_cut', '待裁边'
    PENDING_REVIEW = 'pending_review', '待审核'
    READY_BIND = 'ready_bind', '可装册'
    DETAINED = 'detained', '留置中'


TRANSITIONS = {
    StatusChoices.PENDING_PRESS: [StatusChoices.PRESSING, StatusChoices.DETAINED],
    StatusChoices.PRESSING: [StatusChoices.PENDING_CUT, StatusChoices.DETAINED],
    StatusChoices.PENDING_CUT: [StatusChoices.PENDING_REVIEW, StatusChoices.DETAINED],
    StatusChoices.PENDING_REVIEW: [StatusChoices.READY_BIND, StatusChoices.PENDING_CUT, StatusChoices.DETAINED],
    StatusChoices.READY_BIND: [StatusChoices.DETAINED],
    StatusChoices.DETAINED: [
        StatusChoices.PENDING_PRESS,
        StatusChoices.PRESSING,
        StatusChoices.PENDING_CUT,
        StatusChoices.PENDING_REVIEW,
        StatusChoices.READY_BIND,
    ],
}


class PaperSpec(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='规格名称')
    width = models.IntegerField(verbose_name='宽度(mm)')
    height = models.IntegerField(verbose_name='高度(mm)')
    description = models.CharField(max_length=200, blank=True, verbose_name='描述')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '幅面规格'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.name}({self.width}×{self.height})'


class PressPlate(models.Model):
    code = models.CharField(max_length=30, unique=True, verbose_name='板位编号')
    location = models.CharField(max_length=100, verbose_name='存放位置')
    capacity = models.IntegerField(default=100, verbose_name='最大承载量(张)')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '压平板位'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.code


class ReviewRule(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='规则名称')
    max_warp_count = models.IntegerField(default=2, verbose_name='最大翘边数')
    max_break_count = models.IntegerField(default=3, verbose_name='最大破口数')
    max_press_minutes = models.IntegerField(default=120, verbose_name='最大压平时长(分钟)')
    break_cluster_threshold = models.IntegerField(default=5, verbose_name='同批破口集中阈值')
    pending_review_hours = models.IntegerField(default=24, verbose_name='待审核超时(小时)')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '复核规则'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first() or cls.objects.first()


class BindingPlan(models.Model):
    plan_code = models.CharField(max_length=50, unique=True, verbose_name='装册计划号')
    target_quantity = models.IntegerField(verbose_name='目标册数')
    planned_date = models.DateField(verbose_name='计划日期')
    operator = models.CharField(max_length=50, verbose_name='负责人')
    remark = models.CharField(max_length=300, blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '装册计划'
        verbose_name_plural = verbose_name
        ordering = ['-planned_date']

    def __str__(self):
        return self.plan_code


class PaperBatch(models.Model):
    batch_no = models.CharField(max_length=50, unique=True, verbose_name='批号')
    spec = models.ForeignKey(PaperSpec, on_delete=models.PROTECT, related_name='batches', verbose_name='幅面规格')
    quantity = models.IntegerField(verbose_name='纸张数量(张)')
    plate = models.ForeignKey(PressPlate, on_delete=models.PROTECT, null=True, blank=True, related_name='batches', verbose_name='压平板位')
    binding_plan = models.ForeignKey(BindingPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='batches', verbose_name='所属装册计划')
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.PENDING_PRESS, verbose_name='状态')
    operator = models.CharField(max_length=50, verbose_name='负责人')

    press_start = models.DateTimeField(null=True, blank=True, verbose_name='压平开始时间')
    press_end = models.DateTimeField(null=True, blank=True, verbose_name='压平结束时间')

    warp_count = models.IntegerField(default=0, verbose_name='翘边数')
    warp_note = models.CharField(max_length=500, blank=True, verbose_name='翘边说明')

    break_count = models.IntegerField(default=0, verbose_name='破口数')
    break_detail = models.CharField(max_length=500, blank=True, verbose_name='破口记录详情')

    detain_reason = models.CharField(max_length=500, blank=True, verbose_name='留置原因')
    detained_at = models.DateTimeField(null=True, blank=True, verbose_name='留置时间')
    previous_status = models.CharField(max_length=20, choices=StatusChoices.choices, null=True, blank=True)

    reject_reason = models.CharField(max_length=500, blank=True, verbose_name='驳回原因')
    reject_count = models.IntegerField(default=0, verbose_name='驳回次数')

    review_operator = models.CharField(max_length=50, blank=True, verbose_name='审核人')
    review_at = models.DateTimeField(null=True, blank=True, verbose_name='审核时间')

    bind_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='装册确认时间')
    bind_confirmed_by = models.CharField(max_length=50, blank=True, verbose_name='装册确认人')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '纸张批次'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return self.batch_no

    def can_transition(self, new_status):
        return new_status in TRANSITIONS.get(self.status, [])

    def transition(self, new_status, **kwargs):
        if not self.can_transition(new_status):
            raise ValidationError(f'不能从{self.get_status_display()}流转到{dict(StatusChoices.choices).get(new_status, new_status)}')
        StatusHistory.objects.create(
            batch=self,
            from_status=self.status,
            to_status=new_status,
            operator=kwargs.get('operator', self.operator),
            remark=kwargs.get('remark', ''),
        )
        if self.status == StatusChoices.DETAINED and new_status != StatusChoices.DETAINED:
            self.detained_at = None
            self.detain_reason = ''
        if new_status == StatusChoices.DETAINED:
            self.previous_status = self.status
            self.detained_at = timezone.now()
        self.status = new_status
        self.save()

    @property
    def press_duration_minutes(self):
        if self.press_start and self.press_end:
            return int((self.press_end - self.press_start).total_seconds() / 60)
        if self.press_start and self.status == StatusChoices.PRESSING:
            return int((timezone.now() - self.press_start).total_seconds() / 60)
        return 0


class StatusHistory(models.Model):
    batch = models.ForeignKey(PaperBatch, on_delete=models.CASCADE, related_name='status_histories', verbose_name='批次')
    from_status = models.CharField(max_length=20, choices=StatusChoices.choices, verbose_name='原状态')
    to_status = models.CharField(max_length=20, choices=StatusChoices.choices, verbose_name='目标状态')
    operator = models.CharField(max_length=50, verbose_name='操作人')
    remark = models.CharField(max_length=500, blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='操作时间')

    class Meta:
        verbose_name = '状态变更历史'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.batch.batch_no}: {self.from_status} -> {self.to_status}'


class BreakRecord(models.Model):
    batch = models.ForeignKey(PaperBatch, on_delete=models.CASCADE, related_name='break_records', verbose_name='批次')
    sheet_no = models.IntegerField(verbose_name='张号')
    position = models.CharField(max_length=100, verbose_name='位置')
    length_mm = models.IntegerField(default=0, verbose_name='长度(mm)')
    operator = models.CharField(max_length=50, verbose_name='记录人')
    remark = models.CharField(max_length=300, blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '破口记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.batch.batch_no} 第{self.sheet_no}张 {self.position}'


class AnomalyAlert(models.Model):
    ALERT_TYPES = (
        ('break_cluster', '同批号破口集中'),
        ('press_timeout', '压平时间过长'),
        ('plate_conflict', '板位冲突'),
        ('review_missing', '审核遗漏'),
    )
    batch = models.ForeignKey(PaperBatch, on_delete=models.CASCADE, related_name='alerts', null=True, blank=True, verbose_name='批次')
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES, verbose_name='异常类型')
    message = models.CharField(max_length=500, verbose_name='异常描述')
    extra = models.JSONField(default=dict, blank=True, verbose_name='附加信息')
    is_resolved = models.BooleanField(default=False, verbose_name='是否已处理')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '异常告警'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_alert_type_display()}: {self.message[:50]}'
