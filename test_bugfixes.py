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
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def patch(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PATCH'
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def put(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PUT'
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def delete(url):
    req = urllib.request.Request(
        url,
        headers={'Content-Type': 'application/json'},
        method='DELETE'
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def get(url, params=None):
    if params:
        qs = urllib.parse.urlencode(params)
        url = f"{url}?{qs}"
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())

BASE = 'http://localhost:8123/api'

print('=' * 70)
print('BUG 修复验证测试')
print('=' * 70)

# 先找一个待审核的批次和待裁边的批次
_, r = get(f'{BASE}/batches/', {'status': 'pending_review'})
pending_review_id = r['results'][0]['id'] if r['count'] > 0 else None
pending_review_batch_no = r['results'][0]['batch_no'] if r['count'] > 0 else None
print(f"待审核批次 ID: {pending_review_id}, 批号: {pending_review_batch_no}")

_, r = get(f'{BASE}/batches/', {'status': 'pending_cut'})
pending_cut_id = r['results'][0]['id'] if r['count'] > 0 else None
pending_cut_batch_no = r['results'][0]['batch_no'] if r['count'] > 0 else None
print(f"待裁边批次 ID: {pending_cut_id}, 批号: {pending_cut_batch_no}")

# 先获取一个批次用于测试
_, r = get(f'{BASE}/batches/')
test_id = r['results'][0]['id']
print(f"通用测试批次 ID: {test_id}")

print()
print('-' * 70)
print('【BUG 1】禁止通过通用 PUT/PATCH 接口直接修改批次状态')
print('-' * 70)

code, resp = patch(f'{BASE}/batches/{test_id}/', {'status': 'ready_bind'})
if code in [403, 405]:
    print(f"✅ PATCH 已禁止: HTTP {code}, 错误: {resp.get('error') or resp.get('detail')}")
else:
    print(f"❌ PATCH 未禁止: HTTP {code}, resp: {resp}")

code, resp = put(f'{BASE}/batches/{test_id}/', {
    'batch_no': 'HACKED',
    'spec': 1,
    'quantity': 100,
    'operator': 'hacker',
    'status': 'ready_bind'
})
if code in [403, 405]:
    print(f"✅ PUT 已禁止: HTTP {code}, 错误: {resp.get('error') or resp.get('detail')}")
else:
    print(f"❌ PUT 未禁止: HTTP {code}, resp: {resp}")

code, resp = delete(f'{BASE}/batches/{test_id}/')
if code in [403, 405]:
    print(f"✅ DELETE 已禁止: HTTP {code}, 错误: {resp.get('error') or resp.get('detail')}")
else:
    print(f"❌ DELETE 未禁止: HTTP {code}, resp: {resp}")

print()
print('-' * 70)
print('【BUG 2】审核时校验翘边/破口阈值，超过则不能通过')
print('-' * 70)

# 先查看规则
_, rule = get(f'{BASE}/rules/active/')
print(f"规则: 翘边阈值={rule['max_warp_count']}, 破口阈值={rule['max_break_count']}")

# 先找一个待审核的批次，或者创建测试数据
if pending_review_id:
    _, batch_detail = get(f'{BASE}/batches/{pending_review_id}/')
    print(f"批次 {pending_review_batch_no} 当前: 翘边={batch_detail['warp_count']}, 破口={batch_detail['break_count']}")

    if batch_detail['warp_count'] > rule['max_warp_count'] or batch_detail['break_count'] > rule['max_break_count']:
        # 尝试审核通过，应该被拒绝
        code, resp = post(f'{BASE}/batches/{pending_review_id}/review/', {
            'operator': '测试员',
            'passed': True,
            'reason': '测试超阈值通过'
        })
        if code == 400 and ('翘边数' in resp.get('error', '') or '破口数' in resp.get('error', '')):
            print(f"✅ 超阈值审核通过已禁止: HTTP {code}, 错误: {resp['error']}")
        else:
            print(f"❌ 超阈值审核通过未禁止: HTTP {code}, resp: {resp}")

        # 审核驳回应该正常
        code, resp = post(f'{BASE}/batches/{pending_review_id}/review/', {
            'operator': '测试员',
            'passed': False,
            'reason': '测试驳回'
        })
        if code == 200 and resp['status'] == 'pending_cut':
            print(f"✅ 审核驳回正常: 状态={resp['status_display']}, 驳回次数={resp['reject_count']}")
        else:
            print(f"❌ 审核驳回异常: HTTP {code}, resp: {resp}")
    else:
        print(f"⚠️  该批次未超阈值，跳过此测试场景")

print()
print('-' * 70)
print('【BUG 3】通用破口接口新增/删除时，批次 break_count 自动同步')
print('-' * 70)

# 找一个批次测试
_, r = get(f'{BASE}/batches/')
break_test_id = r['results'][1]['id'] if len(r['results']) > 1 else r['results'][0]['id']
_, bd = get(f'{BASE}/batches/{break_test_id}/')
old_count = bd['break_count']
print(f"批次 ID={break_test_id} 初始 break_count={old_count}")

# 新增一条破口记录
code, resp = post(f'{BASE}/breaks/', {
    'batch': break_test_id,
    'sheet_no': 999,
    'position': '测试位置',
    'length_mm': 5,
    'operator': '测试员'
})
if code == 201:
    break_id = resp['id']
    _, bd2 = get(f'{BASE}/batches/{break_test_id}/')
    new_count = bd2['break_count']
    if new_count == old_count + 1:
        print(f"✅ 新增破口后 break_count 同步: {old_count} -> {new_count}")
    else:
        print(f"❌ 新增破口后 break_count 未同步: {old_count} -> {new_count}")

    # 删除这条破口记录
    code, _ = delete(f'{BASE}/breaks/{break_id}/')
    if code == 204:
        _, bd3 = get(f'{BASE}/batches/{break_test_id}/')
        final_count = bd3['break_count']
        if final_count == old_count:
            print(f"✅ 删除破口后 break_count 同步: {new_count} -> {final_count}")
        else:
            print(f"❌ 删除破口后 break_count 未同步: {new_count} -> {final_count}")
    else:
        print(f"❌ 删除破口失败: HTTP {code}")
else:
    print(f"❌ 新增破口失败: HTTP {code}, resp: {resp}")

print()
print('-' * 70)
print('【BUG 4】待审核状态禁止提交裁边结果，仅待裁边状态允许')
print('-' * 70)

# 先确保有一个待审核的批次
_, r = get(f'{BASE}/batches/', {'status': 'pending_review'})
if r['count'] > 0:
    pending_review_id = r['results'][0]['id']
    pending_review_batch_no = r['results'][0]['batch_no']

    # 尝试在待审核状态提交裁边结果
    code, resp = post(f'{BASE}/batches/{pending_review_id}/cut-result/', {
        'operator': '测试员',
        'warp_count': 0,
        'break_count': 0,
        'remark': '测试待审核提交裁边'
    })
    if code == 400 and '待裁边状态' in resp.get('error', ''):
        print(f"✅ 待审核状态提交裁边已禁止: HTTP {code}, 错误: {resp['error']}")
    else:
        print(f"❌ 待审核状态提交裁边未禁止: HTTP {code}, resp: {resp}")
else:
    print("⚠️  没有待审核的批次，跳过此测试")

# 找一个待裁边的批次，验证可以正常提交
_, r = get(f'{BASE}/batches/', {'status': 'pending_cut'})
if r['count'] > 0:
    pending_cut_id = r['results'][0]['id']
    pending_cut_batch_no = r['results'][0]['batch_no']
    # 获取当前翘边破口数
    _, bd = get(f'{BASE}/batches/{pending_cut_id}/')
    old_warp = bd['warp_count']
    old_break = bd['break_count']

    # 先提交裁边（这会把状态变成待审核）
    code, resp = post(f'{BASE}/batches/{pending_cut_id}/cut-result/', {
        'operator': '测试员',
        'warp_count': 1,
        'warp_note': '测试翘边',
        'break_count': 1,
        'break_detail': '测试破口',
        'remark': '正常裁边提交'
    })
    if code == 200 and resp['status'] == 'pending_review':
        print(f"✅ 待裁边状态提交裁边正常: {pending_cut_batch_no} 状态={resp['status_display']}")
        # 再尝试提交一次，应该被拒绝
        code2, resp2 = post(f'{BASE}/batches/{pending_cut_id}/cut-result/', {
            'operator': '测试员',
            'warp_count': 0,
            'break_count': 0,
        })
        if code2 == 400:
            print(f"✅ 进入待审核后再次提交裁边已禁止: HTTP {code2}, 错误: {resp2['error']}")
        else:
            print(f"❌ 进入待审核后再次提交裁边未禁止: HTTP {code2}, resp: {resp2}")
    else:
        print(f"❌ 待裁边状态提交裁边异常: HTTP {code}, resp: {resp}")
else:
    print("⚠️  没有待裁边的批次，跳过此测试")

print()
print('=' * 70)
print('全部 BUG 修复验证完成')
print('=' * 70)
