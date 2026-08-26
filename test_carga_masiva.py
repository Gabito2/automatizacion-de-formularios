"""
Script de prueba para carga masiva de estudiantes y documentos.
Uso: python test_carga_masiva.py
Requiere: pip install requests
El servidor debe estar corriendo en http://127.0.0.1:8000
"""

import requests
import csv
import os
import random
import string
import json
import io
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

# ── Colores para la consola ──────────────────────────────────────────────────
ROJO = "\033[91m"
VERDE = "\033[92m"
AMARILLO = "\033[93m"
AZUL = "\033[94m"
RESET = "\033[0m"


def log_ok(msg):
    print(f"{VERDE}[OK]{RESET} {msg}")


def log_err(msg):
    print(f"{ROJO}[ERROR]{RESET} {msg}")


def log_info(msg):
    print(f"{AZUL}[INFO]{RESET} {msg}")


def log_warn(msg):
    print(f"{AMARILLO}[WARN]{RESET} {msg}")


# ── 1. Login como admin ──────────────────────────────────────────────────────
def login_admin():
    log_info("Iniciando sesion como administrador...")
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "dni": "10000000",
        "password": "admin123"
    })
    if r.status_code != 200:
        log_err(f"Login fallido: {r.status_code} - {r.text}")
        return None
    data = r.json()
    log_ok(f"Login exitoso. Token obtenido.")
    return data["access_token"]


# ── 2. Generar CSV de prueba ────────────────────────────────────────────────
def generar_csv_test(n=10):
    """Genera un CSV con n estudiantes de prueba."""
    carreras = [
        "Ingenieria en Sistemas",
        "Licenciatura en Educacion",
        "Abogacia",
        "Contador Publico",
        "Medicina",
        "Arquitectura",
    ]
    sedes = ["Sede Centro", "Sede Villa Union", "Sede San Francisco"]
    nombres = ["Juan", "Maria", "Lucas", "Ana", "Pedro", "Laura", "Carlos",
               "Sofia", "Mateo", "Camila", "Diego", "Valentina", "Martin",
               "Isabella", "Santiago", "Emma", "Tomas", "Catalina", "Luciano",
               "Paula"]
    apellidos = ["Perez", "Gomez", "Diaz", "Lopez", "Garcia", "Martinez",
                 "Rodriguez", "Fernandez", "Lopez", "Sanchez", "Ramirez",
                 "Torres", "Flores", "Rivera", "Gomez", "Diaz", "Cruz",
                 "Morales", "Reyes", "Ortiz"]

    dni_base = 40000000
    rows = []
    for i in range(n):
        nombre = random.choice(nombres)
        apellido = random.choice(apellidos)
        dni = str(dni_base + random.randint(0, 9999999))
        email = f"{nombre.lower()}.{apellido.lower()}{dni[-3:]}@test.com"
        carrera = random.choice(carreras)
        sede = random.choice(sedes)
        rows.append({
            "nombre": nombre,
            "apellido": apellido,
            "dni": dni,
            "email": email,
            "carrera": carrera,
            "sede": sede,
        })

    # Escribir CSV en memoria
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["nombre", "apellido", "dni", "email", "carrera", "sede"])
    writer.writeheader()
    writer.writerows(rows)

    # Tambien guardamos a disco para referencia
    filepath = os.path.join(os.path.dirname(__file__), "test_estudiantes.csv")
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        f.write(output.getvalue())
    log_info(f"CSV generado con {n} estudiantes en: {filepath}")
    return output.getvalue(), rows


# ── 3. Carga masiva via /admin/importar-estudiantes ─────────────────────────
def test_importar_estudiantes(token, csv_content):
    log_info("Probando carga masiva via /admin/importar-estudiantes...")
    files = {
        "file": ("estudiantes.csv", csv_content, "text/csv")
    }
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{BASE_URL}/admin/importar-estudiantes",
                      files=files, headers=headers)

    if r.status_code == 200:
        data = r.json()
        log_ok(f"Importacion completada: {data.get('creados', 0)} estudiantes creados.")
        errores = data.get("errores", [])
        if errores:
            log_warn(f"Errores ({len(errores)}):")
            for e in errores:
                print(f"   - {e}")
        return data
    else:
        log_err(f"Importacion fallida: {r.status_code} - {r.text}")
        return None


# ── 4. Login como estudiante y verificar estado ─────────────────────────────
def test_login_estudiante(dni, password):
    """Prueba login de un estudiante creado por importacion."""
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "dni": dni,
        "password": password
    })
    return r.status_code == 200


# ── 5. Verificar legajos via admin ──────────────────────────────────────────
def test_listar_legajos(token):
    log_info("Listando legajos via /admin/legajos...")
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/admin/legajos", headers=headers)

    if r.status_code == 200:
        legajos = r.json()
        log_ok(f"Se encontraron {len(legajos)} legajos.")
        for leg in legajos[:5]:  # Mostrar solo los primeros 5
            estado = leg.get("estado_general", "?")
            nombre = leg.get("nombre", "?")
            apellido = leg.get("apellido", "?")
            dni = leg.get("dni", "?")
            docs = len(leg.get("documentos", []))
            print(f"   {dni} - {nombre} {apellido} | Estado: {estado} | Docs: {docs}")
        if len(legajos) > 5:
            print(f"   ... y {len(legajos) - 5} mas.")
        return legajos
    else:
        log_err(f"Listar legajos fallido: {r.status_code} - {r.text}")
        return []


# ── 6. Crear estudiante con registro individual + documentos ────────────────
def test_registro_individual(token):
    log_info("Probando registro individual de estudiante...")
    dni = str(random.randint(50000000, 59999999))
    password = "".join(random.choices(string.ascii_letters + string.digits, k=10))

    # Crear archivos dummy para simular documentos
    dummy_image = b'\xff\xd8\xff\xe0' + b'\x00' * 500  # JPEG header + datos dummy

    data = {
        "dni": dni,
        "nombre": "Test",
        "apellido": "Individual",
        "email": f"test{dni}@example.com",
        "carrera": "Ingenieria en Sistemas",
        "sede": "Sede Centro",
        "telefono": "351-1234567",
        "direccion": "Calle Falsa 123",
        "localidad": "Cordoba",
        "provincia": "Cordoba",
        "fecha_nacimiento": "2000-01-15",
        "secundario_completo": "true",
        "titulo_secundario": "Bachiller",
        "password": password,
    }

    files = {
        "dni_frente": ("dni_frente.jpg", dummy_image, "image/jpeg"),
        "dni_dorso": ("dni_dorso.jpg", dummy_image, "image/jpeg"),
    }

    r = requests.post(f"{BASE_URL}/auth/register", data=data, files=files)

    if r.status_code in (200, 201):
        resp = r.json()
        log_ok(f"Estudiante registrado: DNI {dni}")
        log_info(f"   Credenciales: DNI={dni}, password={password}")

        # Verificar login
        if test_login_estudiante(dni, password):
            log_ok(f"Login del estudiante DNI {dni} verificado.")
        else:
            log_warn(f"No se pudo loguear el estudiante DNI {dni}.")
        return dni, password
    else:
        log_err(f"Registro fallido: {r.status_code} - {r.text}")
        return None, None


# ── 7. Subir documentos de un estudiante ────────────────────────────────────
def test_subir_documento(token_estudiante):
    log_info("Probando subida de documento como estudiante...")
    headers = {"Authorization": f"Bearer {token_estudiante}"}
    dummy = b'\xff\xd8\xff\xe0' + b'\x00' * 1000

    tipos = ["dni_frente", "dni_dorso", "foto_4x4"]
    for tipo in tipos:
        files = {"file": (f"{tipo}.jpg", dummy, "image/jpeg")}
        data = {"tipo_documento": tipo}
        r = requests.post(f"{BASE_URL}/estudiante/documentos",
                          data=data, files=files, headers=headers)
        if r.status_code in (200, 201):
            log_ok(f"Documento '{tipo}' subido correctamente.")
        else:
            log_warn(f"Documento '{tipo}': {r.status_code} - {r.text}")


# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  TEST DE CARGA MASIVA - Sistema de Legajos UNdeC")
    print("=" * 60)
    print()

    # Verificar que el servidor esta corriendo
    try:
        r = requests.get(f"{BASE_URL}/", timeout=3)
        if r.status_code != 200:
            log_err("El servidor no responde correctamente.")
            return
    except requests.ConnectionError:
        log_err("No se pudo conectar al servidor. Asegurate de que uvicorn este corriendo en el puerto 8000.")
        return
    log_ok("Servidor detectado correctamente.")
    print()

    # Login admin
    token = login_admin()
    if not token:
        return
    print()

    # Generar CSV y carga masiva
    n_estudiantes = 10
    log_info(f"Generando CSV con {n_estudiantes} estudiantes de prueba...")
    csv_content, rows_generados = generar_csv_test(n_estudiantes)
    print()

    resultado = test_importar_estudiantes(token, csv_content)
    print()

    # Listar legajos
    legajos = test_listar_legajos(token)
    print()

    # Registro individual
    dni_ind, pass_ind = test_registro_individual(token)
    print()

    print("=" * 60)
    print("  RESUMEN DE LA PRUEBA")
    print("=" * 60)
    if resultado:
        print(f"  Carga masiva: {resultado.get('creados', 0)} estudiantes creados")
        errores = resultado.get("errores", [])
        if errores:
            print(f"  Errores: {len(errores)}")
    if dni_ind:
        print(f"  Registro individual: DNI {dni_ind}")
    print(f"  Total legajos en sistema: {len(legajos)}")
    print()
    print("  Prueba completada.")
    print()


if __name__ == "__main__":
    main()
