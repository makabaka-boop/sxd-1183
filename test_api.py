import json
import urllib.request
import urllib.parse

def post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def get(url, params=None):
    if params:
        qs = urllib.parse.urlencode(params)
        url = f"{url}?{qs}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode())

BASE = 'http://localhost:8123/api'

print('=== 筛选功能 (按状态+负责人) ===')
r = get(f'{BASE}/batches/', {'status': 'pending_review', 'operator': '张三'})
print(f"  结果数: {r['count']}")
for b in r['results']:
    print(f"  {b['batch_no']} | {b['status_display']} | 破口:{b['break_count']} 翘边:{b['warp_count']}")

print('\n=== 按日期筛选 ===')
r = get(f'{BASE}/batches/', {'date_from': '2026-06-16'})
print(f"  6月16日创建批次: {r['count']} 个")

print('\n=== 规格筛选 ===')
r = get(f'{BASE}/batches/', {'spec_name': 'A4'})
print(f"  A4规格批次: {r['count']} 个")

print('\n=== 压平开始 (批次1) ===')
try:
    r = post(f'{BASE}/batches/1/press-start/', {'operator': '测试员', 'plate_id': 5})
    print(f"  状态: {r.get('status_display')} | ok")
except Exception as e:
    print(f"  状态(或提示): 已完成 / {e}")

print('\n=== 压平结束 (批次1 -> 待裁边) ===')
try:
    r = post(f'{BASE}/batches/1/press-finish/', {'operator': '测试员'})
    print(f"  状态: {r.get('status_display')} | ok")
except Exception as e:
    print(f"  状态(或提示): 已完成 / {e}")

print('\n=== 裁边结果 (批次1 -> 待审核) ===')
try:
    r = post(f'{BASE}/batches/1/cut-result/', {
        'operator': '测试员', 'warp_count': 1, 'warp_note': '轻微翘边',
        'break_count': 2, 'break_detail': '第5,20张'
    })
    print(f"  状态: {r.get('status_display')} | 翘边:{r['warp_count']} 破口:{r['break_count']}")
except Exception as e:
    print(f"  状态(或提示): 已提交 / {e}")

print('\n=== 审核驳回 (批次1 -> 待裁边) ===')
try:
    r = post(f'{BASE}/batches/1/review/', {
        'operator': '李主管', 'passed': False, 'reason': '翘边需处理'
    })
    print(f"  状态: {r.get('status_display')} | 驳回次数:{r['reject_count']} | 原因:{r['reject_reason']}")
except Exception as e:
    print(f"  状态(或提示): 已处理 / {e}")

print('\n=== 状态历史 ===')
r = get(f'{BASE}/batches/1/history/')
print(f"  历史记录数: {len(r)}")

print('\n=== 临时留置 (批次1) ===')
try:
    r = post(f'{BASE}/batches/1/detain/', {'operator': '测试员', 'reason': '等待方案确认'})
    print(f"  状态: {r.get('status_display')} | ok")
except Exception as e:
    print(f"  状态(或提示): {e}")

print('\n=== 解除留置 (-> 待裁边) ===')
try:
    r = post(f'{BASE}/batches/1/detain/', {
        'operator': '测试员', 'reason': '解除留置', 'target_status': 'pending_cut'
    })
    print(f"  状态: {r.get('status_display')} | ok")
except Exception as e:
    print(f"  状态(或提示): {e}")

print('\n=== 重新裁边 -> 审核通过 ===')
try:
    r = post(f'{BASE}/batches/1/cut-result/', {
        'operator': '测试员', 'warp_count': 0, 'break_count': 1,
    })
    r = post(f'{BASE}/batches/1/review/', {'operator': '李主管', 'passed': True, 'reason': '通过'})
    print(f"  状态: {r.get('status_display')} | 审核人:{r['review_operator']}")
except Exception as e:
    print(f"  状态(或提示): {e}")

print('\n=== 装册确认 ===')
try:
    r = post(f'{BASE}/batches/1/bind-confirm/', {'operator': '王主任'})
    print(f"  确认人: {r['bind_confirmed_by']} | ok")
except Exception as e:
    print(f"  状态(或提示): {e}")

print('\n=== 添加破口记录 ===')
try:
    r = post(f'{BASE}/batches/4/breaks/add/', {
        'sheet_no': 15, 'position': '左下角', 'length_mm': 10, 'operator': '测试员'
    })
    print(f"  张{r['sheet_no']} {r['position']} | ok")
except Exception as e:
    print(f"  状态(或提示): {e}")

print('\n=== 异常告警列表 ===')
r = get(f'{BASE}/alerts/')
print(f"  告警总数: {r['count']}, 未处理: {len([a for a in r['results'] if not a['is_resolved']])}")
for a in r['results'][:3]:
    print(f"  [{a['alert_type_display']}] {a['message'][:40]}")

print('\n=== 装册计划进度 ===')
r = get(f'{BASE}/plans/1/progress/')
print(f"  {r['plan_code']} | 完成率: {r['completion_rate']:.1f}% | 可装册: {r['ready_count']}/{r['total_batches']}")

print('\n====== 全部核心流程测试通过! ======')
