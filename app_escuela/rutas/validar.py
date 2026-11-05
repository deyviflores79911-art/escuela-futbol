"""Validaciones de formularios en el servidor (las del navegador se pueden saltar)."""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import abort

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def existe_o_404(valor):
    """Si el registro pedido no existe, responde "No encontrado" (404)."""
    if not valor:
        abort(404)
    return valor


class Errores(dict):
    """Diccionario campo -> mensaje. Vacío = todo bien."""


def texto(form, campo, errores, nombre, obligatorio=True, maximo=100):
    valor = (form.get(campo) or "").strip()
    if obligatorio and not valor:
        errores[campo] = f"{nombre} es obligatorio."
    elif len(valor) > maximo:
        errores[campo] = f"{nombre} admite como máximo {maximo} caracteres."
    return valor or None


def correo(form, campo, errores, obligatorio=True):
    valor = (form.get(campo) or "").strip().lower()
    if obligatorio and not valor:
        errores[campo] = "El correo es obligatorio."
    elif valor and (not _CORREO.match(valor) or len(valor) > 100):
        errores[campo] = "Escribe un correo válido, por ejemplo nombre@escuela.com."
    return valor or None


def clave(form, campo, errores, obligatorio=True, campo_repetir=None):
    valor = form.get(campo) or ""
    if not valor and not obligatorio:
        return None
    if len(valor) < 8:
        errores[campo] = "La contraseña debe tener al menos 8 caracteres."
    elif campo_repetir and form.get(campo_repetir) != valor:
        errores[campo_repetir] = "Las contraseñas no coinciden."
    return valor


def entero(form, campo, errores, nombre, minimo=None, maximo=None, obligatorio=True):
    valor = (form.get(campo) or "").strip()
    if not valor:
        if obligatorio:
            errores[campo] = f"{nombre} es obligatorio."
        return None
    if not re.fullmatch(r"-?\d+", valor):
        errores[campo] = f"{nombre} debe ser un número entero."
        return None
    numero = int(valor)
    if (minimo is not None and numero < minimo) or (maximo is not None and numero > maximo):
        errores[campo] = f"{nombre} debe estar entre {minimo} y {maximo}."
    return numero


def monto(form, campo, errores, nombre, minimo=Decimal("0.01"), maximo=Decimal("99999999.99")):
    """Monto en Bs con hasta dos decimales; acepta coma o punto decimal."""
    valor = (form.get(campo) or "").strip().replace(",", ".")
    if not valor:
        errores[campo] = f"{nombre} es obligatorio."
        return None
    try:
        numero = Decimal(valor)
    except InvalidOperation:
        errores[campo] = f"{nombre} debe ser un número, por ejemplo 250 o 250,50."
        return None
    if numero.as_tuple().exponent < -2:
        errores[campo] = f"{nombre} admite como máximo dos decimales."
    elif numero < minimo:
        errores[campo] = f"{nombre} debe ser mayor a cero."
    elif numero > maximo:
        errores[campo] = f"{nombre} es demasiado grande."
    return numero


def fecha(form, campo, errores, nombre, obligatorio=True, maxima=None):
    """Fecha del formulario (aaaa-mm-dd, como la envía el navegador)."""
    valor = (form.get(campo) or "").strip()
    if not valor:
        if obligatorio:
            errores[campo] = f"{nombre} es obligatoria."
        return None
    try:
        resultado = datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        errores[campo] = f"{nombre} no es una fecha válida."
        return None
    if resultado.year < 1900 or (maxima and resultado > maxima):
        errores[campo] = f"{nombre} no puede ser futura." if maxima else f"{nombre} no es válida."
    return resultado


def hora(form, campo, errores, nombre):
    valor = (form.get(campo) or "").strip()
    try:
        return datetime.strptime(valor[:5], "%H:%M").time()
    except ValueError:
        errores[campo] = f"{nombre} es obligatoria (formato hh:mm)."
        return None


def opcion(form, campo, errores, nombre, opciones, obligatorio=True):
    """El valor debe ser uno de los permitidos (evita valores inventados en el formulario)."""
    valor = (form.get(campo) or "").strip()
    if not valor:
        if obligatorio:
            errores[campo] = f"Elige {nombre}."
        return None
    if valor not in opciones:
        errores[campo] = f"{nombre[0].upper() + nombre[1:]} no es válido."
        return None
    return valor

