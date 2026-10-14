# Direct APK ClickPesa adapter status

`flutter_app` uses a **direct-only** checkout path when compiled with
`--dart-define=BILLING_MODE=clickpesa`.

The backend `app/clickpesa.py` is a **fail-closed, configurable provider adapter**, NOT a preconfigured verified integration. To make it live, configure the Hosted Checkout contract using your particular ClickPesa merchant application credentials and the up-to-date [official ClickPesa API reference](https://docs.clickpesa.com/llms.txt). No API keys are bundled. The adapter intentionally checks provider order ID, amount, currency, and a unique transaction ID before adding any coins; untrusted webhook data only triggers an independent server-side status verification.

Server configuration variable names:

```
PAYMENT_MODE=play,clickpesa
CLICKPESA_API_KEY=...                   # your current ClickPesa authorization token, or supply a working token-refresh integration
CLICKPESA_CREATE_URL=https://...       # provider hosted checkout endpoint
CLICKPESA_CREATE_BODY_TEMPLATE={...}   # JSON fields with ${reference}, ${amount_tzs}, ${currency}, ${user_id}, ${callback_url}
CLICKPESA_AUTH_HEADER=Authorization
CLICKPESA_AUTH_PREFIX=Bearer 
CLICKPESA_CHECKOUT_URL_FIELD=...        # dot-path in create response
CLICKPESA_ORDER_REF_FIELD=...          # dot-path in create response
CLICKPESA_CHECKOUT_HOST=...            # exact permitted provider checkout hostname
CLICKPESA_STATUS_URL_TEMPLATE=https://.../${order_ref}
CLICKPESA_STATUS_FIELD=...             # dot-path in query response
CLICKPESA_PAID_STATUS=...              # provider-confirmed success state
CLICKPESA_REFERENCE_FIELD=...          # your original payment ID in provider's reply
CLICKPESA_AMOUNT_FIELD=...             # expected exactly 1000 TZS
CLICKPESA_CURRENCY_FIELD=...           # expected TZS
CLICKPESA_TRANSACTION_FIELD=...        # verified unique transaction ID
CLICKPESA_WEBHOOK_SECRET=...           # require shared secret in x-clickpesa-webhook-secret if supported
```

**Must implement token refresh if your ClickPesa access token expires**, using exact merchant API credentials, and verify webhook authentication/format against the current provider spec before activation. The current generic template will reject a provider response if the fields do not match: this is intentional. Never assume ClickPass and ClickPesa are the same provider.

If you have the merchant's **client ID, API key configuration, and exact supported webhook contract**, share the configuration **names and example responses with secrets redacted** so this can become a fully verified ClickPesa connector. Do not paste live private keys, password or access tokens into a public chat or GitHub commit.
