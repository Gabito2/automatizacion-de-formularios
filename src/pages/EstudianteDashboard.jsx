import { useState, useEffect } from 'react';
import { estudianteAPI, API_URL } from '../services/api';
import CameraCapture from '../components/CameraCapture';
import { 
  User, FileText, AlertCircle, CheckCircle2, 
  Clock, LogOut, Calendar, Phone, MapPin, Award, 
  Loader2, RefreshCw, HelpCircle, Eye, GraduationCap, Camera
} from 'lucide-react';

export default function EstudianteDashboard({ user, onLogout, onUpdateUser }) {
  // Estado general
  const [profileCompleted, setProfileCompleted] = useState(false);
  const [estadoGeneral, setEstadoGeneral] = useState('incompleto');
  const [documentos, setDocumentos] = useState([]);
  const [observaciones, setObservaciones] = useState([]);
  
  // Carga de vistas
  const [activeTab, setActiveTab] = useState('documentos'); // 'perfil', 'documentos', 'historial'
  const [loading, setLoading] = useState(true);
  const [subiendoDoc, setSubiendoDoc] = useState(null); // almacena tipo_documento en carga
  const [generalError, setGeneralError] = useState('');
  const [profileSuccess, setProfileSuccess] = useState('');
  
  // Estado del formulario de perfil
  const [telefono, setTelefono] = useState('');
  const [direccion, setDireccion] = useState('');
  const [localidad, setLocalidad] = useState('');
  const [provincia, setProvincia] = useState('');
  const [fechaNacimiento, setFechaNacimiento] = useState('');
  const [secundarioCompleto, setSecundarioCompleto] = useState(false);
  const [tituloSecundario, setTituloSecundario] = useState('');

  // Reporte OCR en tiempo real de la subida actual
  const [ocrFeedback, setOcrFeedback] = useState(null);

  // Control de modal de cámara
  const [camaraDocumento, setCamaraDocumento] = useState(null); // tipo_documento | null

  // Estados para corrección de datos del DNI
  const [corrigiendoDatosDni, setCorrigiendoDatosDni] = useState(false);
  const [formDni, setFormDni] = useState('');
  const [formNombre, setFormNombre] = useState('');
  const [formApellido, setFormApellido] = useState('');
  const [formFechaNac, setFormFechaNac] = useState('');
  const [actualizandoDatosDniLoading, setActualizandoDatosDniLoading] = useState(false);
  const [correctionError, setCorrectionError] = useState('');
  const [correctionSuccess, setCorrectionSuccess] = useState('');

  const initCorregirForm = () => {
    setFormDni(ocrFeedback?.datos_extraidos?.dni || user.dni || '');
    setFormNombre(ocrFeedback?.datos_extraidos?.nombre || user.nombre || '');
    setFormApellido(ocrFeedback?.datos_extraidos?.apellido || user.apellido || '');
    setFormFechaNac(ocrFeedback?.datos_extraidos?.fecha_nacimiento || fechaNacimiento || '');
    setCorrectionError('');
    setCorrectionSuccess('');
    setCorrigiendoDatosDni(true);
  };

  const handleCorregirDatosDni = async (e) => {
    e.preventDefault();
    if (!formDni || !formNombre || !formApellido || !formFechaNac) {
      setCorrectionError('Por favor complete todos los campos de identidad.');
      return;
    }
    
    setActualizandoDatosDniLoading(true);
    setCorrectionError('');
    setCorrectionSuccess('');
    
    try {
      const response = await estudianteAPI.actualizarDatosDni({
        dni: formDni,
        nombre: formNombre,
        apellido: formApellido,
        fecha_nacimiento: formFechaNac
      });
      
      setCorrectionSuccess(response.message);
      
      // Actualizar el estado global en App.jsx para propagar los cambios
      if (onUpdateUser) {
        onUpdateUser({
          ...user,
          dni: formDni,
          nombre: formNombre,
          apellido: formApellido
        });
      }
      
      // Recargar información del dashboard
      await cargarInformacion();
      
      // Cerrar editor después de un momento
      setTimeout(() => {
        setCorrigiendoDatosDni(false);
        setOcrFeedback(null); // Limpiar feedback OCR ya corregido
      }, 2000);
      
    } catch (err) {
      setCorrectionError(err.response?.data?.detail || 'Error al actualizar sus datos de identidad.');
    } finally {
      setActualizandoDatosDniLoading(false);
    }
  };

  // Cargar estado inicial
  const cargarInformacion = async () => {
    setLoading(true);
    setGeneralError('');
    try {
      // 1. Obtener estado general del legajo y documentos
      const resEstado = await estudianteAPI.getEstado();
      setEstadoGeneral(resEstado.estado_general);
      setDocumentos(resEstado.documentos);
      setObservaciones(resEstado.observaciones);
      setProfileCompleted(resEstado.datos_personales_completos);

      // 2. Obtener datos personales si ya existen
      const resPerfil = await estudianteAPI.getPerfil();
      if (resPerfil && Object.keys(resPerfil).length > 0) {
        setTelefono(resPerfil.telefono || '');
        setDireccion(resPerfil.direccion || '');
        setLocalidad(resPerfil.localidad || '');
        setProvincia(resPerfil.provincia || '');
        setFechaNacimiento(resPerfil.fecha_nacimiento || '');
        setSecundarioCompleto(resPerfil.secundario_completo || false);
        setTituloSecundario(resPerfil.titulo_secundario || '');
      }
    } catch {
      setGeneralError('Error al conectar con el servidor para obtener los datos.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargarInformacion();
  }, []);

  // Guardar datos personales
  const handleSaveProfile = async (e) => {
    e.preventDefault();
    if (!telefono || !direccion || !localidad || !provincia || !fechaNacimiento || !tituloSecundario) {
      setGeneralError('Por favor complete todos los campos obligatorios del formulario.');
      return;
    }
    
    setGeneralError('');
    setProfileSuccess('');
    try {
      await estudianteAPI.savePerfil({
        telefono,
        direccion,
        localidad,
        provincia,
        fecha_nacimiento: fechaNacimiento,
        secundario_completo: secundarioCompleto,
        titulo_secundario: tituloSecundario
      });
      setProfileSuccess('Datos personales guardados exitosamente.');
      setProfileCompleted(true);
      
      // Recargar para actualizar el estado general
      const resEstado = await estudianteAPI.getEstado();
      setEstadoGeneral(resEstado.estado_general);
    } catch {
      setGeneralError('Ocurrió un error al guardar sus datos personales.');
    }
  };

  // Subir un documento
  const handleFileUpload = async (tipo_documento, e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    // Validar localmente formato
    const allowed = ['.pdf', '.jpg', '.jpeg', '.png'];
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowed.includes(ext)) {
      alert('Formato no permitido. Solo se aceptan PDFs e imágenes (JPG/PNG).');
      return;
    }
    
    // Validar tamaño (10MB)
    if (file.size > 10 * 1024 * 1024) {
      alert('El archivo no debe pesar más de 10MB.');
      return;
    }

    setSubiendoDoc(tipo_documento);
    setOcrFeedback(null);
    setGeneralError('');

    try {
      const response = await estudianteAPI.uploadDocumento(tipo_documento, file);
      
      // Si arrojó análisis OCR
      if (response.ocr_analizado && response.ocr_resultados) {
        setOcrFeedback({
          tipo: tipo_documento,
          resultados: response.ocr_resultados,
          datos_extraidos: response.ocr_datos_extraidos,
          calidad: response.calidad_reporte
        });
      }

      // Actualizar listado de documentos
      await cargarInformacion();
    } catch (err) {
      setGeneralError(err.response?.data?.detail || 'Error al subir el documento de legajo.');
    } finally {
      setSubiendoDoc(null);
    }
  };

  // Subir documento capturado desde cámara
  const handleCamaraUpload = async (blob, dataUrl, tipo_documento) => {
    setCamaraDocumento(null);
    setSubiendoDoc(tipo_documento);
    setOcrFeedback(null);
    setGeneralError('');
    try {
      const response = await estudianteAPI.uploadDocumentoCamara(tipo_documento, dataUrl, 'camara.jpg');
      if (response.ocr_analizado && response.ocr_resultados) {
        setOcrFeedback({
          tipo: tipo_documento,
          resultados: response.ocr_resultados,
          datos_extraidos: response.ocr_datos_extraidos,
          calidad: response.calidad_reporte
        });
      }
      await cargarInformacion();
    } catch (err) {
      setGeneralError(err.response?.data?.detail || 'Error al subir la captura de cámara.');
    } finally {
      setSubiendoDoc(null);
    }
  };

  const nombresDocumentos = {
    dni_frente: 'DNI Frente',
    dni_dorso: 'DNI Dorso',
    foto_4x4: 'Foto Carnet 4x4',
    analitico_secundario: 'Analítico Secundario',
    partida_nacimiento: 'Partida de Nacimiento',
    formulario_inscripcion: 'Formulario de Inscripción'
  };

  const descripcionesDocumentos = {
    dni_frente: 'Lado frontal visible con datos y foto. Formato JPG, PNG o PDF.',
    dni_dorso: 'Lado trasero del documento de identidad. Formato JPG, PNG o PDF.',
    foto_4x4: 'Foto formal tipo carnet del estudiante con fondo claro.',
    analitico_secundario: 'Título secundario original o constancia de título en trámite.',
    partida_nacimiento: 'Copia legible y legalizada de la partida de nacimiento.',
    formulario_inscripcion: 'Planilla de preinscripción provista por el sistema SIU.'
  };

  // Renderizador de estado general en UI
  const getBadgeEstadoGeneral = () => {
    switch (estadoGeneral) {
      case 'aprobado':
        return <span className="badge badge-aprobado"><CheckCircle2 size={14} /> Legajo Aprobado</span>;
      case 'observado':
        return <span className="badge badge-observado"><AlertCircle size={14} /> Legajo Observado</span>;
      case 'pendiente':
        return <span className="badge badge-pendiente"><Clock size={14} /> Validación Pendiente</span>;
      default:
        return <span className="badge badge-incompleto"><HelpCircle size={14} /> Documentación Incompleta</span>;
    }
  };

  if (loading && documentos.length === 0) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '1rem' }}>
        <Loader2 className="spinner-primary spinner" />
        <p style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Cargando portal de legajos...</p>
      </div>
    );
  }

  return (
    <div className="layout-container">
      {/* NAVBAR */}
      <header className="navbar">
        <div className="navbar-brand">
          <GraduationCap size={28} />
          <span>UNdeC</span> Legajos Digitales
        </div>
        <div className="navbar-menu">
          <div className="navbar-user-info">
            <span className="navbar-user-name">{user.nombre} {user.apellido}</span>
            <span className="navbar-user-role">{user.rol} - {user.carrera}</span>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={onLogout} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <LogOut size={16} /> Salir
          </button>
        </div>
      </header>

      {/* DASHBOARD GRID */}
      <main className="dashboard-grid animate-fade-in">
        {/* SIDEBAR */}
        <aside className="sidebar">
          <div className="card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
            <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem', letterSpacing: '0.5px' }}>
              Estado del Trámite
            </h4>
            <div style={{ marginTop: '0.5rem', display: 'flex' }}>
              {getBadgeEstadoGeneral()}
            </div>
            <div style={{ marginTop: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Sede: <strong>{user.sede || 'No especificada'}</strong>
            </div>
          </div>

          <div className="card" style={{ padding: '1rem' }}>
            <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <button 
                className={`sidebar-nav-item ${activeTab === 'perfil' ? 'active' : ''}`}
                onClick={() => setActiveTab('perfil')}
                style={{ background: 'none', border: 'none', width: '100%', textAlign: 'left' }}
              >
                <User size={18} /> Datos Personales
              </button>
              <button 
                className={`sidebar-nav-item ${activeTab === 'documentos' ? 'active' : ''}`}
                onClick={() => setActiveTab('documentos')}
                style={{ background: 'none', border: 'none', width: '100%', textAlign: 'left' }}
              >
                <FileText size={18} /> Legajo Documental
              </button>
              <button 
                className={`sidebar-nav-item ${activeTab === 'historial' ? 'active' : ''}`}
                onClick={() => setActiveTab('historial')}
                style={{ background: 'none', border: 'none', width: '100%', textAlign: 'left' }}
              >
                <AlertCircle size={18} /> Observaciones ({observaciones.length})
              </button>
            </nav>
          </div>
        </aside>

        {/* CONTENIDO PRINCIPAL */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          
          {generalError && (
            <div className="alert alert-danger">
              <AlertCircle size={20} />
              <span>{generalError}</span>
            </div>
          )}

          {/* ALERTA DE COMPLETAR PERFIL PRIMERO */}
          {!profileCompleted && activeTab === 'documentos' && (
            <div className="alert alert-warning">
              <AlertCircle size={20} />
              <div>
                <strong>Paso obligatorio previo:</strong>
                <p style={{ margin: 0 }}>Debe completar primero su Ficha de Datos Personales para habilitar el OCR y la validación automática de sus documentos de identidad.</p>
                <button 
                  className="btn btn-accent btn-sm" 
                  onClick={() => setActiveTab('perfil')} 
                  style={{ marginTop: '0.5rem', padding: '0.3rem 0.7rem' }}
                >
                  Completar Datos Personales
                </button>
              </div>
            </div>
          )}

          {/* TAB: DATOS PERSONALES */}
          {activeTab === 'perfil' && (
            <div className="card animate-fade-in">
              <h3 className="card-title"><User size={20} /> Ficha de Datos Personales</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1.5rem' }}>
                Complete los siguientes campos obligatorios. Estos datos serán comparados por nuestro motor inteligente OCR contra su DNI.
              </p>
              
              {profileSuccess && (
                <div className="alert alert-success">
                  <CheckCircle2 size={20} />
                  <span>{profileSuccess}</span>
                </div>
              )}

              <form onSubmit={handleSaveProfile}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="tel">Teléfono de Contacto *</label>
                    <div style={{ position: 'relative' }}>
                      <Phone size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                      <input id="tel" type="tel" className="form-control" style={{ paddingLeft: '2.5rem' }} value={telefono} onChange={(e) => setTelefono(e.target.value)} required />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="nac">Fecha de Nacimiento *</label>
                    <div style={{ position: 'relative' }}>
                      <Calendar size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                      <input id="nac" type="date" className="form-control" style={{ paddingLeft: '2.5rem' }} value={fechaNacimiento} onChange={(e) => setFechaNacimiento(e.target.value)} required />
                    </div>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="dir">Domicilio Completo (Calle y Altura) *</label>
                  <div style={{ position: 'relative' }}>
                    <MapPin size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                    <input id="dir" type="text" className="form-control" style={{ paddingLeft: '2.5rem' }} value={direccion} onChange={(e) => setDireccion(e.target.value)} required />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="loc">Localidad *</label>
                    <input id="loc" type="text" className="form-control" value={localidad} onChange={(e) => setLocalidad(e.target.value)} required />
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="prov">Provincia *</label>
                    <input id="prov" type="text" className="form-control" value={provincia} onChange={(e) => setProvincia(e.target.value)} required />
                  </div>
                </div>

                <hr style={{ border: 'none', borderTop: '1px solid var(--border-color)', margin: '1.5rem 0' }} />

                <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
                  <input 
                    type="checkbox" 
                    id="sec" 
                    checked={secundarioCompleto} 
                    onChange={(e) => setSecundarioCompleto(e.target.checked)} 
                    style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                  />
                  <label htmlFor="sec" className="form-label" style={{ marginBottom: 0, cursor: 'pointer' }}>¿Posee Secundario Completo?</label>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="tit">Título de Educación Secundaria Obtenido *</label>
                  <div style={{ position: 'relative' }}>
                    <Award size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                    <input id="tit" type="text" className="form-control" style={{ paddingLeft: '2.5rem' }} value={tituloSecundario} onChange={(e) => setTituloSecundario(e.target.value)} placeholder="Ej: Bachiller en Ciencias Sociales" required />
                  </div>
                </div>

                <button type="submit" className="btn btn-primary" style={{ padding: '0.7rem 1.5rem', marginTop: '0.5rem' }}>
                  Guardar Datos Personales
                </button>
              </form>
            </div>
          )}

          {/* TAB: LEGAJO DOCUMENTAL */}
          {activeTab === 'documentos' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              
              {/* FEEDBACK OCR EN TIEMPO REAL */}
              {ocrFeedback && (
                <div className="card animate-fade-in" style={{ borderColor: 'var(--primary-light)', backgroundColor: 'var(--primary-glow)', borderStyle: 'solid' }}>
                  <h4 className="card-title" style={{ color: 'var(--primary)', marginBottom: '0.5rem' }}>
                    <RefreshCw size={18} className="spinner" style={{ animationDuration: '3s' }} /> 
                    Análisis Inteligente en Tiempo Real (OCR)
                  </h4>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                    Hemos extraído la información de su <strong>{nombresDocumentos[ocrFeedback.tipo]}</strong> y la validamos contra su perfil:
                  </p>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {/* Tabla comparativa */}
                    <div style={{ background: 'white', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr', gap: '0.5rem', fontWeight: 700, paddingBottom: '0.5rem', borderBottom: '1px solid var(--border-color)', marginBottom: '0.5rem', fontSize: '0.8rem' }}>
                        <span>Campo</span>
                        <span>Registrado</span>
                        <span>Extraído de DNI</span>
                      </div>
                      
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.85rem' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr', gap: '0.5rem', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600 }}>DNI:</span>
                          <span style={{ color: ocrFeedback.resultados.dni_match ? 'inherit' : '#e53e3e', textDecoration: ocrFeedback.resultados.dni_match ? 'none' : 'line-through' }}>
                            {user.dni}
                          </span>
                          <span style={{ color: '#2f855a', fontWeight: 600 }}>
                            {ocrFeedback.datos_extraidos?.dni || '(No leído)'} {ocrFeedback.resultados.dni_match ? '✓' : '⚠️'}
                          </span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr', gap: '0.5rem', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600 }}>Nombre:</span>
                          <span style={{ color: ocrFeedback.resultados.name_match ? 'inherit' : '#e53e3e', textDecoration: ocrFeedback.resultados.name_match ? 'none' : 'line-through' }}>
                            {user.nombre}
                          </span>
                          <span style={{ color: '#2f855a', fontWeight: 600 }}>
                            {ocrFeedback.datos_extraidos?.nombre || '(No leído)'} {ocrFeedback.resultados.name_match ? '✓' : '⚠️'}
                          </span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr', gap: '0.5rem', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600 }}>Apellido:</span>
                          <span style={{ color: ocrFeedback.resultados.lastname_match ? 'inherit' : '#e53e3e', textDecoration: ocrFeedback.resultados.lastname_match ? 'none' : 'line-through' }}>
                            {user.apellido}
                          </span>
                          <span style={{ color: '#2f855a', fontWeight: 600 }}>
                            {ocrFeedback.datos_extraidos?.apellido || '(No leído)'} {ocrFeedback.resultados.lastname_match ? '✓' : '⚠️'}
                          </span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr', gap: '0.5rem', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600 }}>F. Nacimiento:</span>
                          <span style={{ color: ocrFeedback.resultados.dob_match ? 'inherit' : '#e53e3e', textDecoration: ocrFeedback.resultados.dob_match ? 'none' : 'line-through' }}>
                            {fechaNacimiento || '(No cargada)'}
                          </span>
                          <span style={{ color: '#2f855a', fontWeight: 600 }}>
                            {ocrFeedback.datos_extraidos?.fecha_nacimiento || '(No leído)'} {ocrFeedback.resultados.dob_match ? '✓' : '⚠️'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {ocrFeedback.calidad && (
                      <div style={{ fontSize: '0.8rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                        <div>Calidad del Archivo: {ocrFeedback.calidad.legible ? 
                          <span style={{ color: '#38a169', fontWeight: 600 }}>Adecuada para lectura</span> : 
                          <span style={{ color: '#e53e3e', fontWeight: 600 }}>Lectura comprometida (borrosa/mala iluminación)</span>}
                        </div>
                        {!ocrFeedback.resultados.overall_match && (
                          <div style={{ color: '#e53e3e', fontWeight: 500, marginTop: '0.25rem' }}>
                            Advertencia: Se detectaron discrepancias en los datos de identidad. Por favor, corrígelos a continuación para habilitar la aprobación automática de tu legajo.
                          </div>
                        )}
                      </div>
                    )}

                    {!ocrFeedback.resultados.overall_match && !corrigiendoDatosDni && (
                      <button 
                        type="button" 
                        className="btn btn-accent" 
                        style={{ marginTop: '0.5rem', alignSelf: 'flex-start' }}
                        onClick={initCorregirForm}
                      >
                        Corregir datos de mi cuenta
                      </button>
                    )}

                    {corrigiendoDatosDni && (
                      <form onSubmit={handleCorregirDatosDni} style={{ background: 'white', padding: '1.25rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', marginTop: '0.5rem' }}>
                        <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--primary)' }}>Corregir Datos de Identidad</h4>
                        
                        {correctionError && <div className="alert alert-danger" style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem', marginBottom: '0.75rem' }}>{correctionError}</div>}
                        {correctionSuccess && <div className="alert alert-success" style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem', marginBottom: '0.75rem' }}>{correctionSuccess}</div>}

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                          <div className="form-group" style={{ marginBottom: 0 }}>
                            <label className="form-label" style={{ fontSize: '0.75rem', marginBottom: '4px' }}>Nombre</label>
                            <input type="text" className="form-control form-control-sm" value={formNombre} onChange={(e) => setFormNombre(e.target.value)} required />
                          </div>
                          <div className="form-group" style={{ marginBottom: 0 }}>
                            <label className="form-label" style={{ fontSize: '0.75rem', marginBottom: '4px' }}>Apellido</label>
                            <input type="text" className="form-control form-control-sm" value={formApellido} onChange={(e) => setFormApellido(e.target.value)} required />
                          </div>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
                          <div className="form-group" style={{ marginBottom: 0 }}>
                            <label className="form-label" style={{ fontSize: '0.75rem', marginBottom: '4px' }}>DNI</label>
                            <input type="text" className="form-control form-control-sm" value={formDni} onChange={(e) => setFormDni(e.target.value.replace(/\D/g, ''))} required />
                          </div>
                          <div className="form-group" style={{ marginBottom: 0 }}>
                            <label className="form-label" style={{ fontSize: '0.75rem', marginBottom: '4px' }}>Fecha de Nacimiento</label>
                            <input type="date" className="form-control form-control-sm" value={formFechaNac} onChange={(e) => setFormFechaNac(e.target.value)} required />
                          </div>
                        </div>

                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setCorrigiendoDatosDni(false)} disabled={actualizandoDatosDniLoading}>
                            Cancelar
                          </button>
                          <button type="submit" className="btn btn-primary btn-sm" disabled={actualizandoDatosDniLoading} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                            {actualizandoDatosDniLoading ? <Loader2 className="spinner" size={14} /> : 'Guardar y Re-validar'}
                          </button>
                        </div>
                      </form>
                    )}
                  </div>
                </div>
              )}

              <div className="card">
                <h3 className="card-title"><FileText size={20} /> Carga de Documentación Obligatoria</h3>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1.75rem' }}>
                  Todos los archivos deben cargarse en formato JPG, PNG o PDF con un tamaño máximo de 10MB por documento.
                </p>

                <div className="upload-grid">
                  {documentos.map((doc) => {
                    const cargado = doc.cargado;
                    const esObs = doc.estado === 'observado';
                    const esApro = doc.estado === 'aprobado';
                    const subiendo = subiendoDoc === doc.tipo_documento;

                    return (
                      <div key={doc.tipo_documento} className={`upload-slot ${esApro ? 'success' : ''} ${esObs ? 'observed' : ''}`}>
                        <div>
                          <div style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            width: '40px',
                            height: '40px',
                            borderRadius: '50%',
                            backgroundColor: esApro ? 'var(--success-light)' : (esObs ? 'var(--warning-light)' : '#f1f5f9'),
                            color: esApro ? 'var(--success)' : (esObs ? 'var(--warning)' : 'var(--text-muted)'),
                            marginBottom: '0.5rem'
                          }}>
                            <FileText size={20} />
                          </div>
                          
                          <div className="upload-slot-title">{nombresDocumentos[doc.tipo_documento]}</div>
                          <div className="upload-slot-desc">{descripcionesDocumentos[doc.tipo_documento]}</div>
                        </div>

                        {/* Mostrar Observación si corresponde */}
                        {esObs && (
                          <div style={{
                            width: '100%',
                            backgroundColor: 'var(--warning-light)',
                            border: '1px solid var(--warning-border)',
                            borderRadius: 'var(--radius-sm)',
                            padding: '0.5rem',
                            fontSize: '0.75rem',
                            color: 'hsl(38, 92%, 25%)',
                            marginBottom: '0.75rem',
                            textAlign: 'left'
                          }}>
                            <strong>Observación:</strong> "{doc.observacion}"
                          </div>
                        )}

                        <div style={{ width: '100%' }}>
                          {cargado ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
                                {esApro && <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ Aprobado</span>}
                                {doc.estado === 'pendiente' && <span style={{ color: 'var(--info)', fontWeight: 700 }}>⌚ Pendiente</span>}
                                {esObs && <span style={{ color: 'var(--warning)', fontWeight: 700 }}>⚠ Observado</span>}
                                
                                <a 
                                  href={`${API_URL}/${doc.archivo_url}`} 
                                  target="_blank" 
                                  rel="noopener noreferrer"
                                  className="btn btn-secondary btn-sm"
                                  style={{ padding: '0.2rem 0.5rem', display: 'inline-flex', alignItems: 'center', gap: '0.2rem' }}
                                >
                                  <Eye size={12} /> Ver
                                </a>
                              </div>
                              
                              {!esApro && (
                                <label className="btn btn-secondary btn-sm" style={{ width: '100%', cursor: 'pointer' }}>
                                  {subiendo ? <Loader2 className="spinner" /> : 'Reemplazar Archivo'}
                                  <input 
                                    type="file" 
                                    style={{ display: 'none' }} 
                                    onChange={(e) => handleFileUpload(doc.tipo_documento, e)}
                                    disabled={subiendo || !profileCompleted}
                                  />
                                </label>
                              )}
                            </div>
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                              <label className={`btn ${profileCompleted ? 'btn-primary' : 'btn-secondary'} btn-sm`} style={{ width: '100%', cursor: profileCompleted ? 'pointer' : 'not-allowed' }}>
                                {subiendo ? <Loader2 className="spinner" /> : 'Subir Archivo'}
                                {profileCompleted && (
                                  <input 
                                    type="file" 
                                    style={{ display: 'none' }} 
                                    onChange={(e) => handleFileUpload(doc.tipo_documento, e)}
                                    disabled={subiendo}
                                  />
                                )}
                              </label>
                              {profileCompleted && (
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.3rem' }}
                                  onClick={() => setCamaraDocumento(doc.tipo_documento)}
                                  disabled={subiendo}
                                >
                                  <Camera size={14} /> Usar Cámara
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* TAB: HISTORIAL OBSERVACIONES */}
          {activeTab === 'historial' && (
            <div className="card animate-fade-in">
              <h3 className="card-title"><AlertCircle size={20} /> Historial de Observaciones</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1.5rem' }}>
                Detalle de observaciones y devoluciones documentales realizadas por los validadores académicos.
              </p>

              {observaciones.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-muted)' }}>
                  <CheckCircle2 size={40} style={{ color: 'var(--success)', marginBottom: '0.5rem' }} />
                  <p style={{ fontWeight: 600 }}>¡No posee observaciones en su legajo!</p>
                  <p style={{ fontSize: '0.8rem' }}>Todos sus documentos subidos están limpios o aprobados.</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {observaciones.map((obs) => {
                    const esGeneral = obs.tipo_documento === 'general';
                    return (
                      <div key={obs.id} style={{
                        display: 'flex',
                        gap: '1rem',
                        padding: '1rem',
                        borderRadius: 'var(--radius-md)',
                        backgroundColor: esGeneral ? '#ebf8ff' : 'var(--warning-light)',
                        border: `1px solid ${esGeneral ? '#90cdf4' : 'var(--warning-border)'}`,
                      }}>
                        <div style={{ color: esGeneral ? '#3182ce' : 'var(--warning)', marginTop: '0.15rem' }}>
                          <AlertCircle size={20} />
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.25rem' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.9rem', color: esGeneral ? '#2b6cb0' : 'var(--primary)' }}>
                              {esGeneral ? '📢 Comunicación General' : `Documento: ${nombresDocumentos[obs.tipo_documento]}`}
                            </span>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              {new Date(obs.fecha).toLocaleDateString('es-AR')} {new Date(obs.fecha).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>
                          <p style={{ fontSize: '0.85rem', color: 'var(--text-main)', fontStyle: 'italic' }}>
                            "{obs.mensaje}"
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

        </section>
      </main>

      {/* Modal de captura de cámara para documentos */}
      {camaraDocumento && (
        <CameraCapture
          title={`Capturar: ${nombresDocumentos[camaraDocumento] || camaraDocumento}`}
          hint={
            camaraDocumento === 'foto_4x4'
              ? 'Coloque su cara centrada, bien iluminada y mirando a la cámara'
              : 'Coloque el documento centrado, con buena iluminación y sin reflejos'
          }
          onCapture={(blob, dataUrl) => handleCamaraUpload(blob, dataUrl, camaraDocumento)}
          onClose={() => setCamaraDocumento(null)}
          selfie={camaraDocumento === 'foto_4x4'}
        />
      )}
    </div>
  );
}
