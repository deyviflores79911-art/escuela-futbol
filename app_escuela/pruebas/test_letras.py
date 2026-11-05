"""Montos en letras del recibo."""
import unittest
from decimal import Decimal

from datos.letras import monto_en_letras


class PruebasLetras(unittest.TestCase):
    def test_montos(self):
        casos = {
            "0": "Cero 00/100 Bolivianos",
            "10.08": "Diez 08/100 Bolivianos",
            "16": "Dieciséis 00/100 Bolivianos",
            "21": "Veintiuno 00/100 Bolivianos",
            "31": "Treinta y uno 00/100 Bolivianos",
            "100": "Cien 00/100 Bolivianos",
            "101": "Ciento uno 00/100 Bolivianos",
            "120.50": "Ciento veinte 50/100 Bolivianos",
            "250": "Doscientos cincuenta 00/100 Bolivianos",
            "1000": "Mil 00/100 Bolivianos",
            "21000": "Veintiún mil 00/100 Bolivianos",
            "31000": "Treinta y un mil 00/100 Bolivianos",
            "1000000": "Un millón 00/100 Bolivianos",
            "2500000.75": "Dos millones quinientos mil 75/100 Bolivianos",
        }
        for monto, esperado in casos.items():
            self.assertEqual(monto_en_letras(Decimal(monto)), esperado, monto)

    def test_redondeo_a_centavos(self):
        self.assertEqual(monto_en_letras(Decimal("99.995")), "Cien 00/100 Bolivianos")


if __name__ == "__main__":
    unittest.main()
