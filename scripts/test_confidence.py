import requests, json

with open(r'D:\AI_Project\DocAssistant\samples\sample_quotation.pdf', 'rb') as f:
    r = requests.post('http://127.0.0.1:8540/api/upload', files={'file': ('sample_quotation.pdf', f, 'application/pdf')})
er = r.json()['extract_result']

stats = {'high': 0, 'medium': 0, 'low': 0}
low_fields = []
for k, v in er.items():
    if isinstance(v, dict) and 'confidence' in v:
        c = v['confidence']
        cls = 'high' if c >= 0.9 else 'medium' if c >= 0.7 else 'low'
        stats[cls] += 1
        if cls == 'low':
            low_fields.append(f'  {k}: value="{v["value"]}", conf={c}')

print('=== 报价单 confidence 分布 ===')
print(json.dumps(stats, indent=2))
print(f'低置信字段 (<0.7) 共 {len(low_fields)} 个:')
for lf in low_fields: print(lf)

print()
print('=== 滴滴电子发票 ===')
with open(r'D:\AI_Project\DocAssistant\samples\滴滴电子发票.pdf', 'rb') as f:
    r2 = requests.post('http://127.0.0.1:8540/api/upload', files={'file': ('滴滴电子发票.pdf', f, 'application/pdf')})
d2 = r2.json()
er2 = d2['extract_result']
print('doc_type:', d2['doc_type'])
print('invoice_type:', er2.get('invoice_type', {}).get('value'))
print('seller:', er2.get('seller_name', {}).get('value'))
print('currency:', er2.get('currency', {}).get('value'))

stats2 = {'high': 0, 'medium': 0, 'low': 0}
low2 = []
for k, v in er2.items():
    if isinstance(v, dict) and 'confidence' in v:
        c = v['confidence']
        cls = 'high' if c >= 0.9 else 'medium' if c >= 0.7 else 'low'
        stats2[cls] += 1
        if cls == 'low':
            low2.append(f'  {k}: value="{v["value"]}", conf={c}')
print('confidence 分布:', json.dumps(stats2))
print(f'低置信 {len(low2)} 个:')
for l in low2: print(l)
