import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'paper_system.settings')
django.setup()

from datetime import date, timedelta
from django.utils import timezone
from api.models import (
    PaperSpec, PressPlate, ReviewRule, BindingPlan,
    PaperBatch, StatusChoices, BreakRecord,
)


def init():
    specs = [
        {'name': 'A4', 'width': 210, 'height': 297, 'description': '标准A4'},
        {'name': 'A3', 'width': 297, 'height': 420, 'description': '标准A3'},
        {'name': 'B5', 'width': 176, 'height': 250, 'description': '标准B5'},
        {'name': '16K', 'width': 195, 'height': 270, 'description': '16开'},
    ]
    spec_objs = []
    for s in specs:
        obj, created = PaperSpec.objects.get_or_create(name=s['name'], defaults=s)
        spec_objs.append(obj)
    print(f'规格: {len(spec_objs)} 条')

    plates = [
        {'code': 'PL-A-01', 'location': '压平区A-1号', 'capacity': 120},
        {'code': 'PL-A-02', 'location': '压平区A-2号', 'capacity': 120},
        {'code': 'PL-B-01', 'location': '压平区B-1号', 'capacity': 100},
        {'code': 'PL-B-02', 'location': '压平区B-2号', 'capacity': 100},
        {'code': 'PL-C-01', 'location': '压平区C-1号', 'capacity': 150},
    ]
    plate_objs = []
    for p in plates:
        obj, created = PressPlate.objects.get_or_create(code=p['code'], defaults=p)
        plate_objs.append(obj)
    print(f'板位: {len(plate_objs)} 条')

    rule, created = ReviewRule.objects.get_or_create(
        name='默认复核规则',
        defaults={
            'max_warp_count': 2,
            'max_break_count': 3,
            'max_press_minutes': 120,
            'break_cluster_threshold': 5,
            'pending_review_hours': 24,
        }
    )
    print(f'复核规则: {rule.name}')

    plans = [
        {
            'plan_code': 'ZP-2026-0601',
            'target_quantity': 50,
            'planned_date': date(2026, 6, 20),
            'operator': '李主管',
            'remark': '6月度第一批装册',
        },
        {
            'plan_code': 'ZP-2026-0602',
            'target_quantity': 80,
            'planned_date': date(2026, 6, 25),
            'operator': '王主任',
            'remark': '6月度第二批装册',
        },
    ]
    plan_objs = []
    for p in plans:
        obj, created = BindingPlan.objects.get_or_create(plan_code=p['plan_code'], defaults=p)
        plan_objs.append(obj)
    print(f'装册计划: {len(plan_objs)} 条')

    if PaperBatch.objects.count() == 0:
        batches_data = [
            {
                'batch_no': 'BATCH-20260616-001',
                'spec': spec_objs[0],
                'quantity': 100,
                'plate': plate_objs[0],
                'binding_plan': plan_objs[0],
                'operator': '张三',
                'status': StatusChoices.PENDING_PRESS,
            },
            {
                'batch_no': 'BATCH-20260616-002',
                'spec': spec_objs[1],
                'quantity': 80,
                'plate': plate_objs[1],
                'binding_plan': plan_objs[0],
                'operator': '李四',
                'status': StatusChoices.PRESSING,
                'press_start': timezone.now() - timedelta(minutes=45),
            },
            {
                'batch_no': 'BATCH-20260616-003',
                'spec': spec_objs[0],
                'quantity': 120,
                'plate': plate_objs[2],
                'binding_plan': plan_objs[0],
                'operator': '王五',
                'status': StatusChoices.PENDING_CUT,
                'press_start': timezone.now() - timedelta(hours=3),
                'press_end': timezone.now() - timedelta(hours=1),
            },
            {
                'batch_no': 'BATCH-20260615-004',
                'spec': spec_objs[2],
                'quantity': 90,
                'plate': plate_objs[3],
                'binding_plan': plan_objs[1],
                'operator': '赵六',
                'status': StatusChoices.PENDING_REVIEW,
                'press_start': timezone.now() - timedelta(hours=20),
                'press_end': timezone.now() - timedelta(hours=19),
                'warp_count': 1,
                'warp_note': '边角轻微翘曲，不影响使用',
                'break_count': 2,
                'break_detail': '第12张左上，第45张右下',
            },
            {
                'batch_no': 'BATCH-20260615-005',
                'spec': spec_objs[0],
                'quantity': 110,
                'plate': plate_objs[0],
                'binding_plan': plan_objs[1],
                'operator': '张三',
                'status': StatusChoices.PENDING_REVIEW,
                'press_start': timezone.now() - timedelta(hours=26),
                'press_end': timezone.now() - timedelta(hours=24),
                'warp_count': 3,
                'warp_note': '翘边严重，需要处理',
                'break_count': 6,
                'break_detail': '多张有破口，集中在第30-40张',
            },
            {
                'batch_no': 'BATCH-20260614-006',
                'spec': spec_objs[3],
                'quantity': 70,
                'plate': plate_objs[4],
                'binding_plan': plan_objs[0],
                'operator': '李四',
                'status': StatusChoices.READY_BIND,
                'press_start': timezone.now() - timedelta(days=2),
                'press_end': timezone.now() - timedelta(days=2) + timedelta(minutes=85),
                'warp_count': 0,
                'break_count': 0,
                'review_operator': '李主管',
                'review_at': timezone.now() - timedelta(days=1),
                'bind_confirmed_at': timezone.now() - timedelta(hours=10),
                'bind_confirmed_by': '王主任',
            },
            {
                'batch_no': 'BATCH-20260614-007',
                'spec': spec_objs[1],
                'quantity': 95,
                'plate': plate_objs[1],
                'binding_plan': plan_objs[1],
                'operator': '王五',
                'status': StatusChoices.DETAINED,
                'press_start': timezone.now() - timedelta(days=2),
                'press_end': timezone.now() - timedelta(days=2) + timedelta(hours=1),
                'detain_reason': '纸张含水率异常，等待重新检测',
                'detained_at': timezone.now() - timedelta(hours=8),
                'previous_status': StatusChoices.PENDING_CUT,
            },
            {
                'batch_no': 'BATCH-20260616-008',
                'spec': spec_objs[0],
                'quantity': 100,
                'plate': plate_objs[2],
                'binding_plan': plan_objs[0],
                'operator': '赵六',
                'status': StatusChoices.PRESSING,
                'press_start': timezone.now() - timedelta(hours=3),
            },
        ]
        for bd in batches_data:
            PaperBatch.objects.create(**bd)
        print(f'批次: {PaperBatch.objects.count()} 条')

        b5 = PaperBatch.objects.get(batch_no='BATCH-20260615-005')
        breaks = [
            {'sheet_no': 31, 'position': '左上角', 'length_mm': 8, 'operator': '王五', 'remark': '裁边时不慎撕裂'},
            {'sheet_no': 33, 'position': '右下角', 'length_mm': 5, 'operator': '王五', 'remark': ''},
            {'sheet_no': 35, 'position': '顶部中间', 'length_mm': 12, 'operator': '王五', 'remark': '原纸缺陷'},
            {'sheet_no': 37, 'position': '左侧边缘', 'length_mm': 6, 'operator': '王五', 'remark': ''},
            {'sheet_no': 38, 'position': '左下角', 'length_mm': 10, 'operator': '王五', 'remark': '压平后出现'},
            {'sheet_no': 40, 'position': '右上角', 'length_mm': 4, 'operator': '王五', 'remark': ''},
        ]
        for br in breaks:
            BreakRecord.objects.create(batch=b5, **br)
        b5.break_count = b5.break_records.count()
        b5.save()
        print(f'破口记录: {BreakRecord.objects.count()} 条')


if __name__ == '__main__':
    init()
    print('初始化完成!')
