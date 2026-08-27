import React, { useState } from 'react';
import { authAPI } from '../services/api';
import CameraCapture from '../components/CameraCapture';
import { 
  GraduationCap, User, Lock, Mail, Phone, MapPin, 
  Award, Calendar, FileText, CheckCircle2, 
  AlertCircle, ArrowRight, ArrowLeft, Loader2, Sparkles, Camera
} from 'lucide-react';

export default function Preinscripcion({ onBackToLogin }) {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [progressMsg, setProgressMsg] = useState('');

  // Paso 1: Datos Personales y de Cuenta
  const [dni, setDni] = useState('');
  const [nombre, setNombre] = useState('');
  const [apellido, setApellido] = useState('');
  const [email, setEmail] = useState('');
  const [telefono, setTelefono] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // Paso 2: Domicilio y Educación
  const [direccion, setDireccion] = useState('');
  const [localidad, setLocalidad] = useState('');
  const [provincia, setProvincia] = useState('');
  const [fechaNacimiento, setFechaNacimiento] = useState('');
  const [secundarioCompleto, setSecundarioCompleto] = useState(true);
  const [tituloSecundario, setTituloSecundario] = useState('');

  // Paso 3: Carrera y Documentos
  const [carrera, setCarrera] = useState('');
  const [dniFrente, setDniFrente] = useState(null);
  const [dniDorso, setDniDorso] = useState(null);
  const [fotoPersona, setFotoPersona] = useState(null);

  // Previsualizaciones locales de imágenes
  const [prevFrente, setPrevFrente] = useState('');
  const [prevDorso, setPrevDorso] = useState('');
  const [prevPersona, setPrevPersona] = useState('');

  // Control de modales de cámara
  const [camaraAbierta, setCamaraAbierta] = useState(null); // 'dni_frente' | 'dni_dorso' | 'foto_persona' | null

  // Estado para la validación de DNI en tiempo real
  const [analizandoDni, setAnalizandoDni] = useState(false);
  const [datosExtraidadosDni, setDatosExtraidadosDni] = useState(null);
  const [discrepanciasDni, setDiscrepanciasDni] = useState(null);

  // Estado para la validación de foto personal en tiempo real
  const [analizandoFoto, setAnalizandoFoto] = useState(false);
  const [resultadoFoto, setResultadoFoto] = useState(null); // { has_face, confidence, message }

  // Estado para archivo compuesto (archivo único con todos los documentos)
  const [archivoCompuesto, setArchivoCompuesto] = useState(null);
  const [prevCompuesto, setPrevCompuesto] = useState('');
  const [analizandoCompuesto, setAnalizandoCompuesto] = useState(false);
  const [documentosDetectados, setDocumentosDetectados] = useState(null);
  const [dniDataCompuesto, setDniDataCompuesto] = useState(null);
  const [usandoModoCompuesto, setUsandoModoCompuesto] = useState(false);

  const normalizarTexto = (text) => {
    if (!text) return '';
    return text.toUpperCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^A-Z0-9]/g, "")
      .trim();
  };

  const comprobarDiscrepancias = (fields, formDni, formNombre, formApellido, formFechaNac) => {
    const normOcrDni = normalizarTexto(fields.dni);
    const normFormDni = normalizarTexto(formDni);
    const dniMatch = normOcrDni === normFormDni || normOcrDni.includes(normFormDni) || normFormDni.includes(normOcrDni);

    const normOcrNombre = normalizarTexto(fields.nombre);
    const normFormNombre = normalizarTexto(formNombre);
    const wordsOcrNombre = normOcrNombre.split(' ').filter(w => w.length > 2);
    const wordsFormNombre = normFormNombre.split(' ').filter(w => w.length > 2);
    const nameMatch = wordsOcrNombre.some(w => wordsFormNombre.includes(w)) || normOcrNombre === normFormNombre;

    const normOcrApellido = normalizarTexto(fields.apellido);
    const normFormApellido = normalizarTexto(formApellido);
    const wordsOcrApellido = normOcrApellido.split(' ').filter(w => w.length > 2);
    const wordsFormApellido = normFormApellido.split(' ').filter(w => w.length > 2);
    const lastnameMatch = wordsOcrApellido.some(w => wordsFormApellido.includes(w)) || normOcrApellido === normFormApellido;

    const dobMatch = fields.fecha_nacimiento === formFechaNac;

    return {
      dni: !dniMatch,
      nombre: !nameMatch,
      apellido: !lastnameMatch,
      fecha_nacimiento: !dobMatch,
      tieneDiscrepancia: !dniMatch || !nameMatch || !lastnameMatch || !dobMatch
    };
  };

  React.useEffect(() => {
    if (datosExtraidadosDni) {
      const disc = comprobarDiscrepancias(
        datosExtraidadosDni,
        dni,
        nombre,
        apellido,
        fechaNacimiento
      );
      setDiscrepanciasDni(disc);
    } else {
      setDiscrepanciasDni(null);
    }
  }, [dni, nombre, apellido, fechaNacimiento, datosExtraidadosDni]);


  const analizarDniFrente = async (file) => {
    setAnalizandoDni(true);
    setDatosExtraidadosDni(null);
    setDiscrepanciasDni(null);
    setError('');
    try {
      const response = await authAPI.analizarDni(file);
      if (response && response.extracted_fields) {
        setDatosExtraidadosDni(response.extracted_fields);
      }
    } catch (err) {
      console.error("Error al pre-analizar DNI:", err);
    } finally {
      setAnalizandoDni(false);
    }
  };

  const analizarFotoPersona = async (file) => {
    setAnalizandoFoto(true);
    setResultadoFoto(null);
    try {
      const response = await authAPI.analizarFoto(file);
      setResultadoFoto(response);
    } catch (err) {
      console.error("Error al pre-analizar foto personal:", err);
      setResultadoFoto({ has_face: null, confidence: 0, message: 'No se pudo validar la foto en este momento.' });
    } finally {
      setAnalizandoFoto(false);
    }
  };

  const analizarArchivoCompuesto = async (file) => {
    setAnalizandoCompuesto(true);
    setDocumentosDetectados(null);
    setDniDataCompuesto(null);
    setError('');
    try {
      const response = await authAPI.analizarArchivoCompuesto(file);
      if (response) {
        setDocumentosDetectados(response.documents || []);
        if (response.dni_data) {
          setDniDataCompuesto(response.dni_data);
        }
      }
    } catch (err) {
      console.error("Error al analizar archivo compuesto:", err);
      setError('No se pudo analizar el archivo compuesto.');
    } finally {
      setAnalizandoCompuesto(false);
    }
  };

  const autoCompletarDesdeCompuesto = () => {
    if (dniDataCompuesto) {
      if (dniDataCompuesto.dni) setDni(dniDataCompuesto.dni);
      if (dniDataCompuesto.nombre) setNombre(dniDataCompuesto.nombre);
      if (dniDataCompuesto.apellido) setApellido(dniDataCompuesto.apellido);
      if (dniDataCompuesto.fecha_nacimiento) setFechaNacimiento(dniDataCompuesto.fecha_nacimiento);
    }
  };

  const handleFileChangeCompuesto = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const allowed = ['.jpg', '.jpeg', '.png', '.pdf'];
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowed.includes(ext)) {
      alert('Formato de archivo no permitido. Seleccione una imagen (.jpg, .png) o un PDF.');
      return;
    }

    setArchivoCompuesto(file);
    setPrevCompuesto(ext !== '.pdf' ? URL.createObjectURL(file) : 'pdf');
    setUsandoModoCompuesto(true);
    // Resetear archivos individuales
    setDniFrente(null);
    setDniDorso(null);
    setFotoPersona(null);
    setPrevFrente('');
    setPrevDorso('');
    setPrevPersona('');
    setDatosExtraidadosDni(null);
    setDiscrepanciasDni(null);
    setResultadoFoto(null);
    // Analizar
    analizarArchivoCompuesto(file);
  };

  // Captura desde cámara
  const handleCamaraCapture = async (blob, dataUrl, tipo) => {
    setCamaraAbierta(null);
    // Crear un File a partir del Blob para mantener compatibilidad con el flujo existente
    const ext = 'jpg';
    const file = new File([blob], `camara_${tipo}.${ext}`, { type: 'image/jpeg' });

    if (tipo === 'dni_frente') {
      setDniFrente(file);
      setPrevFrente(dataUrl);
      // Analizar OCR via endpoint de cámara
      setAnalizandoDni(true);
      setDatosExtraidadosDni(null);
      setDiscrepanciasDni(null);
      setError('');
      try {
        const response = await authAPI.analizarDniCamara(dataUrl, `camara.${ext}`);
        if (response && response.extracted_fields) {
          setDatosExtraidadosDni(response.extracted_fields);
        }
      } catch (err) {
        console.error('Error al analizar DNI desde cámara:', err);
      } finally {
        setAnalizandoDni(false);
      }
    } else if (tipo === 'dni_dorso') {
      setDniDorso(file);
      setPrevDorso(dataUrl);
    } else if (tipo === 'foto_persona') {
      setFotoPersona(file);
      setPrevPersona(dataUrl);
      setAnalizandoFoto(true);
      setResultadoFoto(null);
      try {
        const response = await authAPI.analizarFotoCamara(dataUrl, `camara.${ext}`);
        setResultadoFoto(response);
      } catch (err) {
        console.error('Error al analizar foto desde cámara:', err);
        setResultadoFoto({ has_face: null, confidence: 0, message: 'No se pudo validar la foto en este momento.' });
      } finally {
        setAnalizandoFoto(false);
      }
    }
  };

  const handleFileChange = (e, type) => {
    const file = e.target.files[0];
    if (!file) return;

    // Validar extensión
    const allowed = ['.jpg', '.jpeg', '.png', '.pdf'];
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowed.includes(ext)) {
      alert('Formato de archivo no permitido. Seleccione una imagen (.jpg, .png) o un PDF.');
      return;
    }

    // Si es foto personal, forzar que sea imagen para detección de rostros
    if (type === 'foto_persona' && ext === '.pdf') {
      alert('La foto personal debe ser una imagen (.jpg, .jpeg, .png) para poder validar la biometría facial.');
      return;
    }

    // Asignar archivo
    if (type === 'dni_frente') {
      setDniFrente(file);
      setPrevFrente(ext !== '.pdf' ? URL.createObjectURL(file) : 'pdf');
      // Pre-analizar OCR tanto para imágenes como PDFs
      analizarDniFrente(file);
    } else if (type === 'dni_dorso') {
      setDniDorso(file);
      if (ext !== '.pdf') setPrevDorso(URL.createObjectURL(file));
      else setPrevDorso('pdf');
    } else if (type === 'foto_persona') {
      setFotoPersona(file);
      setPrevPersona(URL.createObjectURL(file));
      // Validar rostro en tiempo real
      analizarFotoPersona(file);
    }
  };

  const handleNextStep = () => {
    setError('');
    if (step === 1) {
      if (!dni || !nombre || !apellido || !email || !telefono || !password || !confirmPassword) {
        setError('Por favor complete todos los campos requeridos.');
        return;
      }
      if (password !== confirmPassword) {
        setError('Las contraseñas no coinciden.');
        return;
      }
      if (password.length < 6) {
        setError('La contraseña debe tener al menos 6 caracteres.');
        return;
      }
      setStep(2);
    } else if (step === 2) {
      if (!direccion || !localidad || !provincia || !fechaNacimiento || !tituloSecundario) {
        setError('Por favor complete todos los campos sobre su domicilio y estudios.');
        return;
      }
      setStep(3);
    }
  };

  const handlePrevStep = () => {
    setError('');
    setStep(prev => prev - 1);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    
    if (!carrera) {
      setError('Por favor seleccione una carrera.');
      return;
    }

    // Validar según el modo
    if (usandoModoCompuesto) {
      if (!archivoCompuesto) {
        setError('Ha seleccionado el modo de archivo compuesto pero no se subió ningún archivo.');
        return;
      }
    } else {
      if (!dniFrente || !dniDorso) {
        setError('Por favor cargue el DNI (frente y dorso).');
        return;
      }
    }

    // La foto de perfil es OPCIONAL: si no pasó la detección facial no se
    // bloquea el envío; el sistema la guarda para revisión manual y el
    // estudiante puede volver a sacarse una foto luego desde su panel.
    if (fotoPersona && resultadoFoto && resultadoFoto.has_face === false) {
      setSuccess('Advertencia: no se detectó un rostro en la foto de perfil. La podrá volver a sacar luego desde su panel de estudiante.');
    }

    setLoading(true);
    setProgressMsg('Iniciando proceso de preinscripción...');

    // Simular mensajes de progreso interactivos para el usuario
    const timers = [
      setTimeout(() => setProgressMsg('Guardando archivos en el legajo digital...'), 1200),
      setTimeout(() => setProgressMsg(usandoModoCompuesto ? 'Procesando documento compuesto...' : 'Procesando foto personal en búsqueda de rostros...'), 2800),
      setTimeout(() => setProgressMsg('Validando datos del DNI con lector OCR...'), 4500),
      setTimeout(() => setProgressMsg('Finalizando registro en base de datos...'), 6200),
    ];

    const formData = new FormData();
    formData.append('dni', dni);
    formData.append('nombre', nombre);
    formData.append('apellido', apellido);
    formData.append('email', email);
    formData.append('carrera', carrera);
    formData.append('sede', 'Sede Los Sarmientos');
    formData.append('telefono', telefono);
    formData.append('direccion', direccion);
    formData.append('localidad', localidad);
    formData.append('provincia', provincia);
    formData.append('fecha_nacimiento', fechaNacimiento);
    formData.append('secundario_completo', secundarioCompleto ? 'true' : 'false');
    formData.append('titulo_secundario', tituloSecundario);
    formData.append('password', password);

    if (usandoModoCompuesto && archivoCompuesto) {
      // Modo compuesto: enviar 1 solo archivo
      formData.append('archivo_compuesto', archivoCompuesto);
    } else {
      // Modo individual
      formData.append('dni_frente', dniFrente);
      formData.append('dni_dorso', dniDorso);
      if (fotoPersona) {
        formData.append('foto_persona', fotoPersona);
      }
    }

    try {
      const res = await authAPI.register(formData);
      // Cancelar simuladores si finaliza antes
      timers.forEach(t => clearTimeout(t));
      setSuccess(res.message || '¡Preinscripción realizada con éxito!');
      // Redirigir después de 3 segundos
      setTimeout(() => {
        onBackToLogin();
      }, 3500);
    } catch (err) {
      timers.forEach(t => clearTimeout(t));
      setError(err.response?.data?.detail || 'Ocurrió un error inesperado al procesar tu preinscripción. Intente nuevamente.');
    } finally {
      setLoading(false);
      setProgressMsg('');
    }
  };

  const carrerasDisponibles = [
    "Ingenieria en Sistemas",
    "Licenciatura en Educacion",
    "Abogacia",
    "Sommelier",
    "Licenciatura en Turismo",
    "Licenciatura en Administracion"
  ];

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, hsl(220, 85%, 15%) 0%, hsl(220, 85%, 25%) 50%, hsl(220, 85%, 35%) 100%)',
      padding: '2rem 1rem',
      position: 'relative',
      overflowX: 'hidden',
      fontFamily: 'sans-serif'
    }}>
      {/* Círculos decorativos de fondo */}
      <div style={{
        position: 'absolute',
        top: '-10%',
        left: '-10%',
        width: '450px',
        height: '450px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, var(--accent-glow) 0%, transparent 70%)',
        pointerEvents: 'none'
      }}></div>
      <div style={{
        position: 'absolute',
        bottom: '-10%',
        right: '-10%',
        width: '500px',
        height: '500px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(255,255,255,0.05) 0%, transparent 70%)',
        pointerEvents: 'none'
      }}></div>

      <div className="card animate-fade-in-up" style={{
        maxWidth: '700px',
        width: '100%',
        padding: '2.5rem',
        borderRadius: 'var(--radius-lg)',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
        border: 'none',
        backgroundColor: 'rgba(255, 255, 255, 0.98)',
        backdropFilter: 'blur(10px)',
        position: 'relative',
        zIndex: 1
      }}>
        {/* Loader Overlay durante envío */}
        {loading && (
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(255,255,255,0.95)',
            zIndex: 10,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 'var(--radius-lg)',
            padding: '2rem',
            textAlign: 'center'
          }}>
            <Loader2 className="spinner spinner-primary" style={{ width: '48px', height: '48px', marginBottom: '1.5rem' }} />
            <h3 style={{ color: 'var(--primary)', fontWeight: 800, marginBottom: '0.5rem' }}>Procesando Preinscripción Inteligente</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', maxWidth: '350px' }}>
              {progressMsg}
            </p>
            <div style={{ width: '200px', height: '4px', backgroundColor: '#e2e8f0', borderRadius: '2px', overflow: 'hidden', marginTop: '1rem' }}>
              <div style={{
                height: '100%',
                backgroundColor: 'var(--primary)',
                width: progressMsg.includes('DNI') ? '75%' : progressMsg.includes('rostros') ? '50%' : progressMsg.includes('archivos') ? '25%' : '95%',
                transition: 'width 0.8s ease-in-out'
              }}></div>
            </div>
          </div>
        )}

        {/* Encabezado */}
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '56px',
            height: '56px',
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'var(--primary-glow)',
            color: 'var(--primary)',
            marginBottom: '0.75rem'
          }}>
            <GraduationCap size={32} />
          </div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)', letterSpacing: '-0.5px' }}>
            Formulario de Preinscripción UNdeC
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Acceso a Carreras de Educación Distancia y Virtual
          </p>

          {/* Indicador de pasos */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1.25rem' }}>
            {[1, 2, 3].map((s) => (
              <div 
                key={s} 
                style={{
                  width: '32px',
                  height: '6px',
                  borderRadius: '3px',
                  backgroundColor: s === step ? 'var(--primary)' : (s < step ? 'var(--success)' : '#e2e8f0'),
                  transition: 'background-color 0.3s ease'
                }}
              />
            ))}
          </div>
        </div>

        {error && (
          <div className="alert alert-danger" style={{ marginBottom: '1.5rem' }}>
            <AlertCircle size={20} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="alert alert-success" style={{ marginBottom: '1.5rem' }}>
            <CheckCircle2 size={20} style={{ flexShrink: 0 }} />
            <span>{success}</span>
          </div>
        )}

        {/* PASO 1: DATOS PERSONALES Y CUENTA */}
        {step === 1 && (
          <div className="animate-fade-in">
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--primary)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <User size={18} /> Datos de Cuenta y Datos Personales
            </h3>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label" htmlFor="reg-nombre">Nombre *</label>
                <input id="reg-nombre" type="text" className="form-control" value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Ej: Juan" />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="reg-apellido">Apellido *</label>
                <input id="reg-apellido" type="text" className="form-control" value={apellido} onChange={(e) => setApellido(e.target.value)} placeholder="Ej: Perez" />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label" htmlFor="reg-dni">Número de DNI (sin puntos) *</label>
                <input id="reg-dni" type="text" className="form-control" value={dni} onChange={(e) => setDni(e.target.value.replace(/\D/g, ''))} placeholder="Ej: 45123456" />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="reg-tel">Teléfono de Contacto *</label>
                <div style={{ position: 'relative' }}>
                  <Phone size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                  <input id="reg-tel" type="tel" className="form-control" style={{ paddingLeft: '2.5rem' }} value={telefono} onChange={(e) => setTelefono(e.target.value)} placeholder="Ej: 3825123456" />
                </div>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="reg-email">Correo Electrónico *</label>
              <div style={{ position: 'relative' }}>
                <Mail size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input id="reg-email" type="email" className="form-control" style={{ paddingLeft: '2.5rem' }} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Ej: juan.perez@correo.com" />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label" htmlFor="reg-pass">Contraseña de acceso *</label>
                <div style={{ position: 'relative' }}>
                  <Lock size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                  <input id="reg-pass" type="password" className="form-control" style={{ paddingLeft: '2.5rem' }} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Mínimo 6 caracteres" />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="reg-confirm">Confirmar Contraseña *</label>
                <div style={{ position: 'relative' }}>
                  <Lock size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                  <input id="reg-confirm" type="password" className="form-control" style={{ paddingLeft: '2.5rem' }} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Repita contraseña" />
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '2rem' }}>
              <button type="button" className="btn btn-secondary" onClick={onBackToLogin}>
                Volver al Login
              </button>
              <button type="button" className="btn btn-primary" onClick={handleNextStep} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                Siguiente <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* PASO 2: DOMICILIO Y EDUCACIÓN */}
        {step === 2 && (
          <div className="animate-fade-in">
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--primary)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <MapPin size={18} /> Datos de Domicilio y Educación Secundaria
            </h3>

            <div className="form-group">
              <label className="form-label" htmlFor="reg-nac">Fecha de Nacimiento *</label>
              <div style={{ position: 'relative' }}>
                <Calendar size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input id="reg-nac" type="date" className="form-control" style={{ paddingLeft: '2.5rem' }} value={fechaNacimiento} onChange={(e) => setFechaNacimiento(e.target.value)} />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="reg-dir">Domicilio Completo (Calle y Altura) *</label>
              <input id="reg-dir" type="text" className="form-control" value={direccion} onChange={(e) => setDireccion(e.target.value)} placeholder="Ej: Av. Principal 123" />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label" htmlFor="reg-loc">Localidad *</label>
                <input id="reg-loc" type="text" className="form-control" value={localidad} onChange={(e) => setLocalidad(e.target.value)} placeholder="Ej: Chilecito" />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="reg-prov">Provincia *</label>
                <input id="reg-prov" type="text" className="form-control" value={provincia} onChange={(e) => setProvincia(e.target.value)} placeholder="Ej: La Rioja" />
              </div>
            </div>

            <hr style={{ border: 'none', borderTop: '1px solid var(--border-color)', margin: '1.5rem 0' }} />

            <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <input 
                type="checkbox" 
                id="reg-sec" 
                checked={secundarioCompleto} 
                onChange={(e) => setSecundarioCompleto(e.target.checked)} 
                style={{ width: '18px', height: '18px', cursor: 'pointer' }}
              />
              <label htmlFor="reg-sec" className="form-label" style={{ marginBottom: 0, cursor: 'pointer' }}>Poseo Secundario Completo</label>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="reg-tit">Título de Educación Secundaria Obtenido *</label>
              <div style={{ position: 'relative' }}>
                <Award size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input id="reg-tit" type="text" className="form-control" style={{ paddingLeft: '2.5rem' }} value={tituloSecundario} onChange={(e) => setTituloSecundario(e.target.value)} placeholder="Ej: Bachiller en Ciencias Sociales" />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '2rem' }}>
              <button type="button" className="btn btn-secondary" onClick={handlePrevStep} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <ArrowLeft size={16} /> Atrás
              </button>
              <button type="button" className="btn btn-primary" onClick={handleNextStep} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                Siguiente <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* PASO 3: CARRERA Y CARGA DOCUMENTAL */}
        {step === 3 && (
          <form onSubmit={handleSubmit} className="animate-fade-in">
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--primary)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileText size={18} /> Carrera de Destino y Validación Biométrica
            </h3>

            <div style={{ marginBottom: '1.5rem' }}>
              <div className="form-group">
                <label className="form-label" htmlFor="reg-carrera">Carrera a Preinscribirse *</label>
                <select 
                  id="reg-carrera" 
                  className="form-control form-select" 
                  value={carrera} 
                  onChange={(e) => setCarrera(e.target.value)}
                  required
                >
                  <option value="">Seleccione carrera</option>
                  {carrerasDisponibles.map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ backgroundColor: 'var(--primary-glow)', border: '1px solid var(--primary-light)', padding: '0.75rem', borderRadius: 'var(--radius-md)', marginBottom: '1.5rem', fontSize: '0.8rem', color: 'var(--primary)' }}>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', fontWeight: 600 }}>
                <Sparkles size={16} /> Validación Automática de DNI
              </div>
              <p style={{ margin: '0.25rem 0 0 0', color: 'var(--text-muted)' }}>
                Puede subir los archivos por separado, o subir un <strong>único archivo</strong> (imagen o PDF) que contenga todos los documentos. El sistema detectará y separará automáticamente cada documento.
              </p>
            </div>

            {/* BOTÓN MODO COMPUESTO */}
            <div style={{ 
              border: usandoModoCompuesto ? '2px solid var(--primary)' : '1px solid var(--border-color)', 
              borderRadius: 'var(--radius-md)', 
              padding: '1rem', 
              backgroundColor: usandoModoCompuesto ? 'var(--primary-glow)' : 'white',
              marginBottom: '1rem',
              transition: 'all 0.3s ease'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div>
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <FileText size={16} /> Opción Rápida: Subir Todo Junto
                  </h4>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Si tiene una foto/escaneo con todos los documentos (DNI frente, dorso, foto), súbalo aquí
                  </span>
                </div>
                <label className="btn btn-primary btn-sm" style={{ cursor: 'pointer', margin: 0 }}>
                  {archivoCompuesto ? 'Cambiar Archivo' : 'Seleccionar Archivo'}
                  <input type="file" style={{ display: 'none' }} accept=".jpg,.jpeg,.png,.pdf" onChange={handleFileChangeCompuesto} />
                </label>
              </div>

              {prevCompuesto && (
                <div style={{ marginTop: '0.75rem' }}>
                  {prevCompuesto === 'pdf' ? (
                    <span style={{ fontSize: '0.8rem', color: 'var(--success)', fontWeight: 600 }}>✓ PDF cargado ({archivoCompuesto.name})</span>
                  ) : (
                    <img src={prevCompuesto} alt="Archivo compuesto" style={{ height: '80px', borderRadius: '4px', border: '1px solid var(--border-color)', objectFit: 'contain' }} />
                  )}
                </div>
              )}

              {analizandoCompuesto && (
                <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--primary)', fontSize: '0.85rem' }}>
                  <Loader2 className="spinner" size={16} />
                  <span>Analizando archivo compuesto...</span>
                </div>
              )}

              {/* Documentos detectados */}
              {documentosDetectados && documentosDetectados.length > 0 && (
                <div style={{ marginTop: '1rem', padding: '0.75rem', borderRadius: 'var(--radius-md)', backgroundColor: '#f0fff4', border: '1px solid #c6f6d5' }}>
                  <h5 style={{ fontSize: '0.8rem', fontWeight: 700, margin: '0 0 0.5rem 0', color: '#276749' }}>
                    Documentos encontrados ({documentosDetectados.length}):
                  </h5>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                    {documentosDetectados.map((doc, idx) => (
                      <span key={idx} style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.3rem',
                        padding: '0.25rem 0.5rem',
                        borderRadius: '999px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        backgroundColor: doc.type === 'dni_frente' ? '#ebf8ff' : doc.type === 'dni_dorso' ? '#fefcbf' : '#fed7e2',
                        color: doc.type === 'dni_frente' ? '#2b6cb0' : doc.type === 'dni_dorso' ? '#975a16' : '#97266d',
                        border: `1px solid ${doc.type === 'dni_frente' ? '#90cdf4' : doc.type === 'dni_dorso' ? '#f6e05e' : '#fbb6ce'}`,
                      }}>
                        <CheckCircle2 size={12} />
                        {doc.type === 'dni_frente' ? 'DNI Frente' : doc.type === 'dni_dorso' ? 'DNI Dorso' : 'Foto Perfil'}
                        <span style={{ fontWeight: 400, fontSize: '0.7rem' }}>({Math.round(doc.confidence * 100)}%)</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Datos del DNI extraídos */}
              {dniDataCompuesto && (
                <div style={{ marginTop: '1rem', padding: '0.75rem', borderRadius: 'var(--radius-md)', backgroundColor: '#ebf8ff', border: '1px solid #90cdf4' }}>
                  <h5 style={{ fontSize: '0.8rem', fontWeight: 700, margin: '0 0 0.5rem 0', color: '#2b6cb0', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                    <Sparkles size={14} /> Datos extraídos del DNI:
                  </h5>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.3rem', fontSize: '0.8rem', marginBottom: '0.75rem' }}>
                    <span><strong>DNI:</strong> {dniDataCompuesto.dni || 'No detectado'}</span>
                    <span><strong>Nombre:</strong> {dniDataCompuesto.nombre || 'No detectado'}</span>
                    <span><strong>Apellido:</strong> {dniDataCompuesto.apellido || 'No detectado'}</span>
                    <span><strong>Fecha Nac.:</strong> {dniDataCompuesto.fecha_nacimiento || 'No detectado'}</span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    style={{ width: '100%' }}
                    onClick={autoCompletarDesdeCompuesto}
                  >
                    Auto-completar formulario con estos datos
                  </button>
                </div>
              )}
            </div>

            {/* SEPARADOR */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', margin: '1rem 0', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
              <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--border-color)' }} />
              <span>O suba archivos por separado</span>
              <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--border-color)' }} />
            </div>

            {/* SECCIÓN DE SUBIDA DE ARCHIVOS INDIVIDUALES */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginBottom: '2rem', opacity: usandoModoCompuesto ? 0.5 : 1, pointerEvents: usandoModoCompuesto ? 'none' : 'auto' }}>
              
              {/* 1. DNI Frente */}
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '1rem', backgroundColor: 'white' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div>
                    <h4 style={{ fontSize: '0.85rem', fontWeight: 700, margin: 0 }}>DNI Frente *</h4>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Imagen frontal del DNI (JPG, PNG o foto)</span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer', margin: 0 }}>
                      {dniFrente ? 'Cambiar Archivo' : 'Cargar Archivo'}
                      <input type="file" style={{ display: 'none' }} accept=".jpg,.jpeg,.png,.pdf" onChange={(e) => handleFileChange(e, 'dni_frente')} />
                    </label>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setCamaraAbierta('dni_frente')}
                      style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                    >
                      <Camera size={14} /> Cámara
                    </button>
                  </div>
                </div>
                {prevFrente && (
                  <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {prevFrente === 'pdf' ? (
                      <span style={{ fontSize: '0.8rem', color: 'var(--success)', fontWeight: 600 }}>✓ PDF cargado ({dniFrente.name})</span>
                    ) : (
                      <img src={prevFrente} alt="DNI Frente" style={{ height: '60px', borderRadius: '4px', border: '1px solid var(--border-color)', objectFit: 'contain' }} />
                    )}
                  </div>
                )}

                {analizandoDni && (
                  <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--primary)', fontSize: '0.85rem' }}>
                    <Loader2 className="spinner" size={16} />
                    <span>Analizando imagen de DNI...</span>
                  </div>
                )}

                {datosExtraidadosDni && discrepanciasDni && (
                  <div style={{
                    marginTop: '1rem',
                    padding: '1rem',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid',
                    borderColor: discrepanciasDni.tieneDiscrepancia ? '#fbd38d' : '#c6f6d5',
                    backgroundColor: discrepanciasDni.tieneDiscrepancia ? '#fffaf0' : '#f0fff4',
                    fontSize: '0.85rem'
                  }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', color: discrepanciasDni.tieneDiscrepancia ? '#dd6b20' : '#38a169', display: 'flex', alignItems: 'center', gap: '0.25rem', fontWeight: 700 }}>
                      {discrepanciasDni.tieneDiscrepancia ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
                      {discrepanciasDni.tieneDiscrepancia ? 'Los datos no coinciden' : 'Datos del DNI coinciden'}
                    </h4>
                    <p style={{ margin: '0 0 1rem 0', color: 'var(--text-muted)' }}>
                      {discrepanciasDni.tieneDiscrepancia 
                        ? 'Se detectaron discrepancias entre los datos ingresados y los de la foto del DNI. Por favor, corrígelos:' 
                        : 'Los datos leídos del DNI coinciden perfectamente con los ingresados.'}
                    </p>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr', gap: '0.5rem', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600 }}>DNI:</span>
                        <span style={{ textDecoration: discrepanciasDni.dni ? 'line-through' : 'none', color: discrepanciasDni.dni ? '#e53e3e' : 'inherit' }}>
                          {dni || '(Vacío)'}
                        </span>
                        <span style={{ color: '#2f855a', fontWeight: 600 }}>
                          {datosExtraidadosDni.dni || '(No detectado)'}
                        </span>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr', gap: '0.5rem', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600 }}>Nombre:</span>
                        <span style={{ textDecoration: discrepanciasDni.nombre ? 'line-through' : 'none', color: discrepanciasDni.nombre ? '#e53e3e' : 'inherit' }}>
                          {nombre || '(Vacío)'}
                        </span>
                        <span style={{ color: '#2f855a', fontWeight: 600 }}>
                          {datosExtraidadosDni.nombre || '(No detectado)'}
                        </span>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr', gap: '0.5rem', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600 }}>Apellido:</span>
                        <span style={{ textDecoration: discrepanciasDni.apellido ? 'line-through' : 'none', color: discrepanciasDni.apellido ? '#e53e3e' : 'inherit' }}>
                          {apellido || '(Vacío)'}
                        </span>
                        <span style={{ color: '#2f855a', fontWeight: 600 }}>
                          {datosExtraidadosDni.apellido || '(No detectado)'}
                        </span>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr', gap: '0.5rem', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600 }}>Fecha Nac.:</span>
                        <span style={{ textDecoration: discrepanciasDni.fecha_nacimiento ? 'line-through' : 'none', color: discrepanciasDni.fecha_nacimiento ? '#e53e3e' : 'inherit' }}>
                          {fechaNacimiento || '(Vacío)'}
                        </span>
                        <span style={{ color: '#2f855a', fontWeight: 600 }}>
                          {datosExtraidadosDni.fecha_nacimiento || '(No detectado)'}
                        </span>
                      </div>
                    </div>

                    {discrepanciasDni.tieneDiscrepancia && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', borderTop: '1px solid #e2e8f0', paddingTop: '1rem' }}>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          style={{ width: '100%' }}
                          onClick={() => {
                            if (datosExtraidadosDni.dni) setDni(datosExtraidadosDni.dni);
                            if (datosExtraidadosDni.nombre) setNombre(datosExtraidadosDni.nombre);
                            if (datosExtraidadosDni.apellido) setApellido(datosExtraidadosDni.apellido);
                            if (datosExtraidadosDni.fecha_nacimiento) setFechaNacimiento(datosExtraidadosDni.fecha_nacimiento);
                          }}
                        >
                          Corregir formulario con datos del DNI
                        </button>
                        
                        <div>
                          <p style={{ fontWeight: 600, fontSize: '0.75rem', marginBottom: '0.25rem', color: 'var(--text-main)' }}>O edita manualmente aquí:</p>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                            <div className="form-group" style={{ marginBottom: 0 }}>
                              <label className="form-label" style={{ fontSize: '0.7rem', marginBottom: '2px' }}>Nombre</label>
                              <input type="text" className="form-control form-control-sm" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} value={nombre} onChange={(e) => setNombre(e.target.value)} />
                            </div>
                            <div className="form-group" style={{ marginBottom: 0 }}>
                              <label className="form-label" style={{ fontSize: '0.7rem', marginBottom: '2px' }}>Apellido</label>
                              <input type="text" className="form-control form-control-sm" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} value={apellido} onChange={(e) => setApellido(e.target.value)} />
                            </div>
                            <div className="form-group" style={{ marginBottom: 0 }}>
                              <label className="form-label" style={{ fontSize: '0.7rem', marginBottom: '2px' }}>DNI</label>
                              <input type="text" className="form-control form-control-sm" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} value={dni} onChange={(e) => setDni(e.target.value.replace(/\D/g, ''))} />
                            </div>
                            <div className="form-group" style={{ marginBottom: 0 }}>
                              <label className="form-label" style={{ fontSize: '0.7rem', marginBottom: '2px' }}>Fecha Nacimiento</label>
                              <input type="date" className="form-control form-control-sm" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} value={fechaNacimiento} onChange={(e) => setFechaNacimiento(e.target.value)} />
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* 2. DNI Dorso */}
              <div style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '1rem', backgroundColor: 'white' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div>
                    <h4 style={{ fontSize: '0.85rem', fontWeight: 700, margin: 0 }}>DNI Dorso *</h4>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Imagen trasera del DNI (JPG, PNG o foto)</span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer', margin: 0 }}>
                      {dniDorso ? 'Cambiar Archivo' : 'Cargar Archivo'}
                      <input type="file" style={{ display: 'none' }} accept=".jpg,.jpeg,.png,.pdf" onChange={(e) => handleFileChange(e, 'dni_dorso')} />
                    </label>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setCamaraAbierta('dni_dorso')}
                      style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                    >
                      <Camera size={14} /> Cámara
                    </button>
                  </div>
                </div>
                {prevDorso && (
                  <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {prevDorso === 'pdf' ? (
                      <span style={{ fontSize: '0.8rem', color: 'var(--success)', fontWeight: 600 }}>✓ PDF cargado ({dniDorso.name})</span>
                    ) : (
                      <img src={prevDorso} alt="DNI Dorso" style={{ height: '60px', borderRadius: '4px', border: '1px solid var(--border-color)', objectFit: 'contain' }} />
                    )}
                  </div>
                )}
              </div>

              {/* 3. Foto Personal / Rostro */}
              <div style={{ border: `1px solid ${resultadoFoto && resultadoFoto.has_face === false ? '#fc8181' : 'var(--border-color)'}`, borderRadius: 'var(--radius-md)', padding: '1rem', backgroundColor: 'white', transition: 'border-color 0.3s ease' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div>
                    <h4 style={{ fontSize: '0.85rem', fontWeight: 700, margin: 0 }}>Foto de Rostro (Foto Carnet/Selfie) <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: '0.75rem' }}>(Opcional)</span></h4>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Debe ser una foto clara de frente de su cara (JPG, PNG)</span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer', margin: 0 }}>
                      {fotoPersona ? 'Cambiar Foto' : 'Cargar Foto'}
                      <input type="file" style={{ display: 'none' }} accept=".jpg,.jpeg,.png" onChange={(e) => handleFileChange(e, 'foto_persona')} />
                    </label>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setCamaraAbierta('foto_persona')}
                      style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                    >
                      <Camera size={14} /> Cámara
                    </button>
                  </div>
                </div>
                {prevPersona && (
                  <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <img src={prevPersona} alt="Rostro" style={{ height: '64px', width: '64px', borderRadius: '50%', border: `2px solid ${resultadoFoto ? (resultadoFoto.has_face ? '#68d391' : resultadoFoto.has_face === false ? '#fc8181' : '#e2e8f0') : '#e2e8f0'}`, objectFit: 'cover', transition: 'border-color 0.3s ease' }} />
                    <div style={{ flex: 1 }}>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block' }}>{fotoPersona.name}</span>

                      {/* Estado de análisis facial */}
                      {analizandoFoto && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.35rem', color: 'var(--primary)', fontSize: '0.8rem' }}>
                          <Loader2 className="spinner" size={14} />
                          <span>Analizando rostro...</span>
                        </div>
                      )}

                      {!analizandoFoto && resultadoFoto && (
                        <div style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.4rem',
                          marginTop: '0.4rem',
                          padding: '0.25rem 0.6rem',
                          borderRadius: '999px',
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          backgroundColor: resultadoFoto.has_face === true ? '#f0fff4' : resultadoFoto.has_face === false ? '#fff5f5' : '#fffff0',
                          color: resultadoFoto.has_face === true ? '#276749' : resultadoFoto.has_face === false ? '#c53030' : '#744210',
                          border: `1px solid ${resultadoFoto.has_face === true ? '#9ae6b4' : resultadoFoto.has_face === false ? '#fc8181' : '#f6e05e'}`,
                        }}>
                          {resultadoFoto.has_face === true && <CheckCircle2 size={13} />}
                          {resultadoFoto.has_face === false && <AlertCircle size={13} />}
                          {resultadoFoto.has_face === null && <AlertCircle size={13} />}
                          <span>{resultadoFoto.message}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '2rem' }}>
              <button type="button" className="btn btn-secondary" onClick={handlePrevStep}>
                Atrás
              </button>
              <button type="submit" className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                Finalizar Preinscripción <CheckCircle2 size={16} />
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Modal de captura de cámara */}
      {camaraAbierta && (
        <CameraCapture
          title={
            camaraAbierta === 'dni_frente' ? 'Capturar DNI Frente' :
            camaraAbierta === 'dni_dorso' ? 'Capturar DNI Dorso' :
            'Capturar Foto Personal'
          }
          hint={
            camaraAbierta === 'foto_persona'
              ? 'Coloque su cara centrada, bien iluminada y mirando a la cámara'
              : 'Coloque el DNI centrado, con buena iluminación y sin reflejos'
          }
          onCapture={(blob, dataUrl) => handleCamaraCapture(blob, dataUrl, camaraAbierta)}
          onClose={() => setCamaraAbierta(null)}
          selfie={camaraAbierta === 'foto_persona'}
        />
      )}
    </div>
  );
}
