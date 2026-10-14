# ClickPass (MyShopii) integration contract

The name ClickPass supplied for this project is **not assumed to be ClickPesa**. Without an actual ClickPass/OpenAPI document, sample initiation request, reconciliation response, and webhook signature convention, it would be unsafe to invent endpoint formats. The adapter is fully isolated in `backend/app/clickpass.py` so wiring it does not affect Flutter UI or entitlements.

## Configure in `.env` / production secrets

- `CLICKPASS_CREATE_URL`: HTTPS create-checkout endpoint
- `CLICKPASS_API_KEY`: server-only API secret
- `CLICKPASS_AUTH_HEADER`: which request header carries the key, e.g., `Authorization`
- `CLICKPASS_AUTH_PREFIX`: e.g., `Bearer ` (trailing space)
- `CLICKPASS_CREATE_BODY_TEMPLATE`: complete **JSON** request object with placeholders. Supported replacements: `${reference}`, `${amount_tzs}`, `${currency}`, `${user_id}`, `${callback_url}`. Exact-key replacements preserve integer amount data type.
- `CLICKPASS_CHECKOUT_URL_FIELD`: dotted path in creation response, e.g., `data.payment_url`
- `CLICKPASS_ORDER_REF_FIELD`: dotted path to provider order ID in creation response
- `CLICKPASS_CHECKOUT_HOST`: exact approved hostname of gateway checkout URL
- `CLICKPASS_STATUS_URL_TEMPLATE`: HTTPS status URL with `${order_ref}` placeholder
- `CLICKPASS_STATUS_FIELD`: dotted path to status, e.g., `data.status`
- `CLICKPASS_PAID_STATUS`: provider's *exact* success state
- `CLICKPASS_REFERENCE_FIELD`: response path to **our** server-generated payment reference
- `CLICKPASS_AMOUNT_FIELD`: response path to amount, in units matching `amount_tzs`
- `CLICKPASS_CURRENCY_FIELD`: response path to currency; must be `TZS`
- `CLICKPASS_TRANSACTION_FIELD`: provider's globally unique settled transaction ID
- `CLICKPASS_WEBHOOK_SECRET`: shared secret passed by gateway as `X-Clickpass-Webhook-Secret`, if supported. **The gateway might use a different signature system; adapt and validate that explicitly.**

**Example only — the field names below are illustrative, NOT the ClickPass API:**

```json
{"reference":"${reference}","amount":"${amount_tzs}","currency":"${currency}","callback":"${callback_url}"}
```

Never treat a client redirect, mobile money STK push initiation, or raw webhook `status=success` as paid. We only credit through `verify_order()` which fetches canonical status directly from the provider, matches amount/currency/reference, and atomically creates a unique ledger credit. A payment is never credited twice even if verification happens multiple times. Configure a trusted webhook trigger and perform a negative and replay test before enabling production money.

For Play Store distribution, use Google Play Billing unless separately eligible for the appropriate alternative billing program. Do not embed secrets into Flutter application code.
