from ollama import Client

client = Client()

SYSTEM_PROMPT = open("strudel_background_prompt.txt").read()

def generate_strudel(paragraph: str, previous_code: str = "") -> str:
    user = (f"PREVIOUS CODE:\n{previous_code}\n\n" if previous_code else "") + \
           f"PARAGRAPH: {paragraph}"

    resp = client.chat(
        model="qwen3.5:4b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        think=False,                 # <-- the line that kills the 120-180s delay
        options={
            "temperature": 0.3,
            "num_predict": 400,      # hard cap on output tokens (see note below)
        },
    )
    return resp["message"]["content"].strip()

if __name__ == "__main__":
    code = generate_strudel("Una cosa era certa: che il micino bianco non c'entrava affatto...")
    print(code)
