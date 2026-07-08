import time
import base64
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Assigned values
TOTAL_ORDERS = 52
RATE_LIMIT = 20
WINDOW_SECONDS = 10

# Storage (in-memory)
idempotency_store = {}
orders_created = {}

rate_limits = {}


# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# Rate limiting middleware
# -------------------------

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):

    client_id = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()

    if client_id not in rate_limits:
        rate_limits[client_id] = []

    # remove old requests
    rate_limits[client_id] = [
        t for t in rate_limits[client_id]
        if now - t < WINDOW_SECONDS
    ]

    if len(rate_limits[client_id]) >= RATE_LIMIT:
        retry_after = int(
            WINDOW_SECONDS - (now - rate_limits[client_id][0])
        )

        return JSONResponse(
            status_code=429,
            headers={
                "Retry-After": str(max(retry_after, 1))
            },
            content={
                "error": "rate limit exceeded"
            }
        )

    rate_limits[client_id].append(now)

    return await call_next(request)



# -------------------------
# Idempotent POST /orders
# -------------------------

@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str = Header(None, alias="Idempotency-Key")
):

    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Missing Idempotency-Key"
            }
        )


    # Existing request
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]


    # Create new order
    new_id = str(len(idempotency_store) + 1)

    order = {
        "id": new_id,
        "item": f"Order {new_id}"
    }

    idempotency_store[idempotency_key] = order

    return order



# -------------------------
# Cursor pagination
# -------------------------

@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: str = None
):

    if limit < 1:
        limit = 1


    # Decode cursor
    if cursor:
        try:
            start = int(
                base64.b64decode(cursor).decode()
            )
        except:
            start = 1
    else:
        start = 1


    end = min(
        start + limit - 1,
        TOTAL_ORDERS
    )


    items = []

    for i in range(start, end + 1):
        items.append(
            {
                "id": i,
                "item": f"Order {i}"
            }
        )


    # More pages available
    if end < TOTAL_ORDERS:

        next_cursor = base64.b64encode(
            str(end + 1).encode()
        ).decode()

    else:
        next_cursor = None


    return {
        "items": items,
        "next_cursor": next_cursor
    }
