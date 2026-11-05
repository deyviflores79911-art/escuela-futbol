"""
Montos en letras para el recibo: 120.50 -> "Ciento veinte 50/100 Bolivianos".
"""
from decimal import ROUND_HALF_UP, Decimal

_UNIDADES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
             "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve",
             "veinte", "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis",
             "veintisiete", "veintiocho", "veintinueve"]
_DECENAS = {30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta", 70: "setenta", 80: "ochenta",
            90: "noventa"}
_CENTENAS = {1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos", 5: "quinientos",
             6: "seiscientos", 7: "setecientos", 8: "ochocientos", 9: "novecientos"}


def _hasta_999(n):
    if n == 100:
        return "cien"
    centena, resto = divmod(n, 100)
    partes = [_CENTENAS[centena]] if centena else []
    if resto < 30:
        if resto or not partes:
            partes.append(_UNIDADES[resto])
    else:
        decena, unidad = divmod(resto, 10)
        partes.append(_DECENAS[decena * 10] + (f" y {_UNIDADES[unidad]}" if unidad else ""))
    return " ".join(partes)


def numero_en_letras(n):
    """Entero de 0 a 999.999.999 en letras ("uno" se apocopa a "un" delante de mil y millón)."""
    if not 0 <= n < 1_000_000_000:
        raise ValueError("Monto fuera de rango")
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        partes.append("un millón" if millones == 1 else _apocopar(_hasta_999(millones)) + " millones")
    if miles:
        partes.append("mil" if miles == 1 else _apocopar(_hasta_999(miles)) + " mil")
    if unidades or not partes:
        partes.append(_hasta_999(unidades))
    return " ".join(partes)


def _apocopar(texto):
    """'veintiuno mil' -> 'veintiún mil'; 'treinta y uno mil' -> 'treinta y un mil'."""
    if texto.endswith("veintiuno"):
        return texto[:-1].replace("veintiun", "veintiún")
    return texto[:-3] + "un" if texto.endswith("uno") else texto


def monto_en_letras(monto, moneda="Bolivianos"):
    """Decimal o número -> 'Ciento veinte 50/100 Bolivianos'."""
    n = Decimal(monto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    entero = int(n)
    centavos = int((n - entero) * 100)
    texto = numero_en_letras(entero)
    return f"{texto[0].upper()}{texto[1:]} {centavos:02d}/100 {moneda}"
