"""Xavfsiz matematik parser — eval() ishlatilmaydi"""

import math
import re
from typing import Union

# Ruxsat etilgan funksiyalar
SAFE_FUNCTIONS = {
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "log": math.log10,
    "ln": math.log,
    "sqrt": math.sqrt,
    "abs": abs,
    "factorial": math.factorial,
}

CONSTANTS = {
    "π": math.pi,
    "pi": math.pi,
    "e": math.e,
}

MAX_NUMBER = 1e15  # Overflow himoya


class CalcError(Exception):
    pass


def tokenize(expr: str) -> list:
    """Ifodani tokenlarga bo'lish"""
    tokens = []
    i = 0
    while i < len(expr):
        ch = expr[i]

        # Bo'shliqni o'tkazish
        if ch.isspace():
            i += 1
            continue

        # Raqam yoki nuqta
        if ch.isdigit() or ch == ".":
            num = ""
            while i < len(expr) and (expr[i].isdigit() or expr[i] == "."):
                num += expr[i]
                i += 1
            tokens.append(("NUM", float(num)))
            continue

        # Funksiya nomi yoki konstanta
        if ch.isalpha() or ch == "π":
            name = ""
            while i < len(expr) and (expr[i].isalpha() or expr[i] == "π"):
                name += expr[i]
                i += 1
            if name in SAFE_FUNCTIONS:
                tokens.append(("FUNC", name))
            elif name in CONSTANTS:
                tokens.append(("NUM", CONSTANTS[name]))
            else:
                raise CalcError(f"Noma'lum: {name}")
            continue

        # Operatorlar
        if ch in "+-":
            tokens.append(("OP", ch))
            i += 1
        elif ch in "×*":
            tokens.append(("OP", "*"))
            i += 1
        elif ch in "÷/":
            tokens.append(("OP", "/"))
            i += 1
        elif ch == "%":
            tokens.append(("OP", "%"))
            i += 1
        elif ch == "^":
            tokens.append(("OP", "^"))
            i += 1
        elif ch == "²":
            tokens.append(("OP", "^"))
            tokens.append(("NUM", 2.0))
            i += 1
        elif ch == "−":
            tokens.append(("OP", "-"))
            i += 1
        elif ch == "(":
            tokens.append(("LPAREN", ch))
            i += 1
        elif ch == ")":
            tokens.append(("RPAREN", ch))
            i += 1
        elif ch == "!":
            tokens.append(("OP", "!"))
            i += 1
        else:
            raise CalcError(f"Noto'g'ri belgi: {ch}")

    return tokens


class Parser:
    """Recursive descent parser"""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected_type=None):
        tok = self.peek()
        if tok is None:
            raise CalcError("Kutilmagan tugash")
        if expected_type and tok[0] != expected_type:
            raise CalcError(f"Kutilgan: {expected_type}, topilgan: {tok[0]}")
        self.pos += 1
        return tok

    def parse(self) -> float:
        result = self.expression()
        if self.pos < len(self.tokens):
            raise CalcError("Ortiqcha belgilar")
        return result

    def expression(self) -> float:
        """Qo'shish va ayirish"""
        left = self.term()
        while self.peek() and self.peek()[0] == "OP" and self.peek()[1] in "+-":
            op = self.consume()[1]
            right = self.term()
            if op == "+":
                left += right
            else:
                left -= right
        return left

    def term(self) -> float:
        """Ko'paytirish va bo'lish"""
        left = self.power()
        while self.peek() and self.peek()[0] == "OP" and self.peek()[1] in "*/":
            op = self.consume()[1]
            right = self.power()
            if op == "*":
                left *= right
            else:
                if right == 0:
                    raise CalcError("Nolga bo'lish mumkin emas!")
                left /= right
        return left

    def power(self) -> float:
        """Daraja"""
        left = self.unary()
        if self.peek() and self.peek()[0] == "OP" and self.peek()[1] == "^":
            self.consume()
            right = self.unary()
            left = left ** right
        return left

    def unary(self) -> float:
        """Unar minus va postfix"""
        if self.peek() and self.peek()[0] == "OP" and self.peek()[1] in "+-":
            op = self.consume()[1]
            val = self.unary()
            result = -val if op == "-" else val
        else:
            result = self.atom()

        # Postfix: !, %
        while self.peek() and self.peek()[0] == "OP" and self.peek()[1] in "!%":
            op = self.consume()[1]
            if op == "!":
                if result < 0 or result != int(result) or result > 170:
                    raise CalcError("Factorial faqat 0-170 oralig'ida")
                result = float(math.factorial(int(result)))
            elif op == "%":
                result = result / 100.0

        return result

    def atom(self) -> float:
        """Raqam, funksiya, qavslar"""
        tok = self.peek()
        if tok is None:
            raise CalcError("Ifoda to'liq emas")

        # Raqam
        if tok[0] == "NUM":
            self.consume()
            return tok[1]

        # Funksiya
        if tok[0] == "FUNC":
            name = self.consume()[1]
            self.consume("LPAREN")
            arg = self.expression()
            self.consume("RPAREN")
            try:
                return SAFE_FUNCTIONS[name](arg)
            except (ValueError, OverflowError) as e:
                raise CalcError(f"{name} xatosi: {e}")

        # Qavslar
        if tok[0] == "LPAREN":
            self.consume()
            val = self.expression()
            self.consume("RPAREN")
            return val

        raise CalcError(f"Kutilmagan: {tok[1]}")


def safe_calc(expression: str) -> Union[str, float]:
    """Asosiy hisoblash funksiyasi"""
    expression = expression.strip()
    if not expression:
        raise CalcError("Bo'sh ifoda")

    # "15% dan 8000" formatini parse qilish
    percent_match = re.match(
        r"([\d.]+)\s*%\s*(?:dan|of|from)\s+([\d.]+)", expression, re.IGNORECASE
    )
    if percent_match:
        percent = float(percent_match.group(1))
        base = float(percent_match.group(2))
        return base * percent / 100

    # Oddiy hisoblash
    tokens = tokenize(expression)
    parser = Parser(tokens)
    result = parser.parse()

    # Overflow tekshiruv
    if abs(result) > MAX_NUMBER:
        raise CalcError("Son juda katta!")

    # Butun son bo'lsa, int qilib ko'rsatish
    if result == int(result) and abs(result) < 1e12:
        return int(result)

    return round(result, 10)


def format_result(value) -> str:
    """Natijani chiroyli formatlash"""
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value == int(value):
            return f"{int(value):,}"
        formatted = f"{value:,.10f}".rstrip("0").rstrip(".")
        return formatted
    return str(value)
