"""Configurable server-to-server gateway contract.

IMPORTANT: ClickPesa Hosted Checkout API mappings must be validated against your merchant configuration. This adapter is
not claiming field names or webhook format for that specific gateway. Configure
its actual API contract and test against its sandbox before live money.
"""
import json
import os
from urllib.parse import quote, urlparse
from decimal import Decimal, InvalidOperation
import httpx

class GatewayError(Exception):
    pass

def configured(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise GatewayError(f'Missing gateway configuration: {name}')
    return value

def https_only(url: str):
    if urlparse(url).scheme != 'https':
        raise GatewayError('Payment provider must use HTTPS')

def read_path(data: dict, path: str):
    value = data
    for part in path.split('.'):
        if not isinstance(value, dict) or part not in value:
            raise GatewayError(f'Expected gateway response field missing: {path}')
        value = value[part]
    return value

def headers():
    value = configured('CLICKPESA_API_KEY')
    name = os.getenv('CLICKPESA_AUTH_HEADER','Authorization')
    prefix = os.getenv('CLICKPESA_AUTH_PREFIX','Bearer ')
    if name.lower() in ('host','cookie','content-length') or '\n' in name:
        raise GatewayError('Unsafe auth header')
    return {name: prefix+value, 'Accept':'application/json'}

def template_replace(value, params):
    if isinstance(value, dict):
        return {k:template_replace(v,params) for k,v in value.items()}
    if isinstance(value, list):
        return [template_replace(v,params) for v in value]
    if isinstance(value, str) and value in params:
        return params[value]
    if isinstance(value,str):
        for k,v in params.items():
            value=value.replace(k,str(v))
    return value

def create_checkout(payment_id: str, amount_tzs: int, user_id: str, callback_url: str):
    """Returns provider checkout URL + gateway order reference only after validated response."""
    url=configured('CLICKPESA_CREATE_URL');https_only(url)
    raw=configured('CLICKPESA_CREATE_BODY_TEMPLATE')
    try: body=json.loads(raw)
    except ValueError: raise GatewayError('Invalid create body JSON template')
    if not isinstance(body,dict): raise GatewayError('Create body must be an object')
    substitutions={
        '${reference}':payment_id, '${amount_tzs}':amount_tzs,
        '${currency}':'TZS', '${user_id}':user_id, '${callback_url}':callback_url}
    body=template_replace(body,substitutions)
    try:
        with httpx.Client(timeout=14, follow_redirects=False) as http:
            response=http.post(url,headers=headers(),json=body)
            response.raise_for_status()
            data=response.json()
        checkout=read_path(data,configured('CLICKPESA_CHECKOUT_URL_FIELD'))
        order_ref=read_path(data,configured('CLICKPESA_ORDER_REF_FIELD'))
        if not isinstance(checkout,str) or not isinstance(order_ref,(str,int)):
            raise GatewayError('Invalid checkout response')
        https_only(checkout)
        # Optional allowlist prevents untrusted checkout redirects from a compromised provider payload.
        allowed=configured('CLICKPESA_CHECKOUT_HOST')
        if urlparse(checkout).hostname != allowed:
            raise GatewayError('Checkout host is not on the allowlist')
        return checkout,str(order_ref)
    except (httpx.HTTPError,ValueError) as exc:
        raise GatewayError('Provider checkout unavailable') from exc

def verify_order(payment_id: str, provider_order_id: str, amount_tzs: int):
    """Reads canonical status from gateway API; verifies reference, amount and currency."""
    url_template=configured('CLICKPESA_STATUS_URL_TEMPLATE')
    url=url_template.replace('${order_ref}',quote(provider_order_id,safe=''))
    https_only(url)
    try:
        with httpx.Client(timeout=14,follow_redirects=False) as http:
            response=http.get(url,headers=headers());response.raise_for_status()
            data=response.json()
        state=str(read_path(data,configured('CLICKPESA_STATUS_FIELD')))
        if state!=configured('CLICKPESA_PAID_STATUS'):
            return None
        ref=str(read_path(data,configured('CLICKPESA_REFERENCE_FIELD')))
        value=read_path(data,configured('CLICKPESA_AMOUNT_FIELD'))
        curr=str(read_path(data,configured('CLICKPESA_CURRENCY_FIELD')))
        txn=str(read_path(data,configured('CLICKPESA_TRANSACTION_FIELD')))
        try:
            amount_matches = not isinstance(value,bool) and Decimal(str(value)) == Decimal(amount_tzs)
        except InvalidOperation:
            amount_matches = False
        if ref!=payment_id or not amount_matches or curr!='TZS' or not txn:
            raise GatewayError('Provider paid receipt does not match expected order')
        return f'clickpesa:{txn}'
    except (httpx.HTTPError,ValueError,TypeError) as exc:
        raise GatewayError('Provider status verification failed') from exc
