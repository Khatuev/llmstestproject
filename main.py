import pandas as pd
from ollama import chat
import re
import io
from contextlib import redirect_stdout

df = pd.read_csv("data/freelancer_earnings_bd.csv")

SYSTEM_PROMPT = """
Ты помощник-аналитик. Пользователь задаёт вопрос по данным фрилансеров.
Ответь ТОЛЬКО кодом на Python, использующим библиотеку pandas и переменную df.

Используй ТОЛЬКО существующие колонки:
['Freelancer_ID', 'Job_Category', 'Platform', 'Experience_Level', 'Client_Region',
 'Payment_Method', 'Job_Completed', 'Earnings_USD', 'Hourly_Rate',
 'Job_Success_Rate', 'Client_Rating', 'Job_Duration_Days', 'Project_Type',
 'Rehire_Rate', 'Marketing_Spend']

Не используй придуманные переменные (например, expert_rate).
Не используй mean(...) отдельно. Всегда используй метод Series или DataFrame: df[...]....mean()
Никаких пояснений, комментариев, markdown или форматирования. Только чистый, исполнимый Python-код.
"""

def clean_code(raw_code: str) -> str:
    import re
    match = re.search(r"```(?:python)?\n(.*?)```", raw_code, re.DOTALL)
    code = match.group(1) if match else raw_code

    lines = []
    for line in code.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(x in line for x in ["```", "#", "Ответ:", "Thus", "print(\"", "print("]):
            continue
        line = line.replace("\\_", "_")
        lines.append(line)

    return "\n".join(lines).strip()


def run_code(code: str) -> str:
    output_buffer = io.StringIO()
    result = None
    exec_globals = {"pd": pd}
    exec_locals = {"df": df}

    invalid_columns = [
        col for col in re.findall(r"df\[['\"](.*?)['\"]\]", code)
        if col not in df.columns
    ]
    if invalid_columns:
        return f"Ошибка: в коде используются несуществующие колонки: {invalid_columns}"

    with redirect_stdout(output_buffer):
        try:
            compiled_expr = compile(code, "<string>", "eval")
        except SyntaxError:
            lines = code.strip().splitlines()
            if not lines:
                return ""
            last_line = lines[-1].strip()
            body = "\n".join(lines[:-1])

            try:
                compiled_last = compile(last_line, "<string>", "eval")
            except SyntaxError:
                match = re.match(r'\s*([A-Za-z_]\w*)\s*=', last_line)
                try:
                    exec(code, exec_globals, exec_locals)
                except Exception as e:
                    return f"Ошибка выполнения: {e}"
                else:
                    if match:
                        var_name = match.group(1)
                        result = exec_locals.get(var_name)
            else:
                try:
                    exec(body, exec_globals, exec_locals)
                    result = eval(last_line, exec_globals, exec_locals)
                except Exception as e:
                    return f"Ошибка выполнения: {e}"
        else:
            try:
                result = eval(compiled_expr, exec_globals, exec_locals)
            except Exception as e:
                return f"Ошибка выполнения: {e}"

    output_text = output_buffer.getvalue().strip()

    if isinstance(result, (float, int)) and (pd.isna(result) or result == float("inf")):
        return "Результат: NaN (возможно, фильтр вернул пустую выборку или деление на 0)"

    if result is not None:
        if output_text:
            output_text += f"\n{result}"
        else:
            output_text = str(result)

    return output_text.strip()

print("Введите ваш вопрос (или 'exit' для выхода):")
while True:
    user_input = input("> ")
    if not user_input or user_input.lower() in ("exit", "quit"):
        print("Выход.")
        break
    try:
        response = chat(
            model="mistral",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ]
        )
        generated_code = response.message.content
    except Exception as e:
        print(f"Ошибка генерации кода: {e}")
        continue
    code_to_run = clean_code(generated_code)
    try:
        output = run_code(code_to_run)
    except Exception as e:
        output = f"Ошибка при выполнении кода: {e}"
    if output is not None:
        print(output)
