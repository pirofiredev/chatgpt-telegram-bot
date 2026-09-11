import json
import logging

import asyncpg

EXTRACT_PROMPT = (
    "You are a memory extractor. Given a conversation exchange, extract any facts "
    "worth remembering long-term about the USER (not the assistant). "
    "Examples: name, age, language preference, interests, mood patterns, important life events.\n\n"
    "Return a JSON object like {\"key\": \"value\", ...} where each key is a short snake_case label "
    "and the value is a concise fact string. Return {} if nothing is worth remembering."
)


async def extract_facts(client, model: str, user_msg: str, bot_msg: str) -> dict:
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": f"User said: {user_msg}\nAssistant replied: {bot_msg}"},
            ],
            max_tokens=300,
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logging.debug(f"[memory] extract_facts failed: {e}")
        return {}


async def save_facts(pool: asyncpg.Pool, user_id: int, facts: dict):
    if not facts:
        return
    async with pool.acquire() as conn:
        for key, value in facts.items():
            await conn.execute(
                "INSERT INTO user_facts(user_id, key, value, updated_at) VALUES($1, $2, $3, now()) "
                "ON CONFLICT(user_id, key) DO UPDATE SET value = $3, updated_at = now()",
                user_id, str(key), str(value),
            )
    logging.debug(f"[memory] saved {len(facts)} fact(s) for user {user_id}: {list(facts.keys())}")


async def load_facts(pool: asyncpg.Pool, user_id: int) -> dict:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value FROM user_facts WHERE user_id = $1 ORDER BY updated_at DESC",
            user_id,
        )
    return {r["key"]: r["value"] for r in rows}


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_facts (
    user_id    BIGINT NOT NULL,
    key        TEXT   NOT NULL,
    value      TEXT   NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, key)
);
"""
