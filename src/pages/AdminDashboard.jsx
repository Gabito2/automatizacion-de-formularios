import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { adminAPI, API_URL, getFileUrl } from '../services/api';
import {
  FileSpreadsheet, Users, FileCheck, FileWarning, Search,
  Filter, Check, X, Eye, LogOut,
  AlertCircle, Info, Sparkles, GraduationCap, UploadCloud,
  Loader2, RefreshCw, FileText, MessageSquare, Send
} from 'lucide-react';

export default function AdminDashboard({ user, onLogout }) {
  // Datos principales
  const [legajos, setLegajos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Filtros
  const [filtroCarrera, setFiltroCarrera] = useState('');
  const [filtroEstado, setFiltroEstado] = useState('');
  const [filtroQuery, setFiltroQuery] = useState('');
  
  // Estudiante Seleccionado para Verificación
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [activeDocPreview, setActiveDocPreview] = useState(null); // Documento que se está previsualizando en panel
  const [mensajeRechazo, setMensajeRechazo] = useState('');
  const [showRechazoModal, setShowRechazoModal] = useState(false);
  const [docToRechazar, setDocToRechazar] = useState(null);
  const [verificandoLoading, setVerificandoLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  
  // Sección de Importación Masiva
  const [showImportPanel, setShowImportPanel] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState(null);

  // Sección de Observación Masiva
  const [showObsModal, setShowObsModal] = useState(false);
  const [obsDestino, setObsDestino] = useState('todos'); // 'todos' | 'deudores' | 'especifico'
  const [obsMensaje, setObsMensaje] = useState('');
  const [obsUsuarioId, setObsUsuarioId] = useState('');
  const [obsBusqueda, setObsBusqueda] = useState('');
  const [obsLoading, setObsLoading] = useState(false);
  const [obsResult, setObsResult] = useState(null);

  // Sección de Registro Individual
  const [showRegistroModal, setShowRegistroModal] = useState(false);
  const [registroLoading, setRegistroLoading] = useState(false);
  const [registroResult, setRegistroResult] = useState(null);
  const [registroForm, setRegistroForm] = useState({
    dni: '',
    nombre: '',
    apellido: '',
    email: '',
    carrera: '',
    telefono: '',
    direccion: '',
    localidad: '',
    provincia: '',
    fecha_nacimiento: ''
  });

  // Estadísticas del Dashboard
  const [stats, setStats] = useState({
    total: 0,
    aprobados: 0,
    observados: 0,
    pendientes: 0,
    incompletos: 0
  });

  const cargarLegajos = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const filters = {};
      if (filtroCarrera) filters.carrera = filtroCarrera;
      if (filtroEstado) filters.estado = filtroEstado;
      if (filtroQuery) filters.query = filtroQuery;
      
      // Una sola llamada para legajos + stats en paralelo
      const [data, statsData] = await Promise.all([
        adminAPI.getLegajos(filters),
        adminAPI.getStats()
      ]);
      setLegajos(data);
      setStats(statsData);
    } catch {
      setError('Error al obtener la lista de legajos.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };  useEffect(() => {
    cargarLegajos(false);
  }, [filtroCarrera, filtroEstado]);

  // Debounce para búsqueda de texto (evita refetch en cada keystroke)
  const debounceTimer = useRef(null);
  const handleQueryChange = useCallback((e) => {
    const val = e.target.value;
    setFiltroQuery(val);
    clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      cargarLegajos(false);
    }, 400);
  }, [filtroCarrera, filtroEstado]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    clearTimeout(debounceTimer.current);
    cargarLegajos(false);
  };

  // Importar archivo
  const handleImportSubmit = async (e) => {
    e.preventDefault();
    if (!importFile) return;
    
    setImportLoading(true);
    setImportResult(null);
    setError('');
    try {
      const res = await adminAPI.importarEstudiantes(importFile);
      setImportResult(res);
      setImportFile(null);
      await cargarLegajos(false); // Recargar dashboard
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al importar los estudiantes.');
    } finally {
      setImportLoading(false);
    }
  };

  // Aprobar un documento
  const handleAprobarDoc = useCallback(async (docId) => {
    setVerificandoLoading(true);
    setError('');
    try {
      await adminAPI.aprobarDocumento(docId);
      
      // Actualizar el estudiante seleccionado localmente
      if (selectedStudent) {
        const updatedDocs = selectedStudent.documentos.map(d => {
          if (d.id === docId) {
            return { ...d, estado: 'aprobado', observacion: null };
          }
          return d;
        });
        
        // Comprobar si completó el legajo (los 6 tipos obligatorios aprobados)
        const tiposObligatorios = ['dni_frente', 'dni_dorso', 'foto_4x4', 'analitico_secundario', 'partida_nacimiento', 'formulario_inscripcion'];
        const tiposPresentes = new Set(updatedDocs.map(d => d.tipo_documento));
        const todosSubidos = tiposObligatorios.every(t => tiposPresentes.has(t));
        const todosAprobados = updatedDocs
          .filter(d => tiposObligatorios.includes(d.tipo_documento))
          .every(d => d.estado === 'aprobado');
        const todoAprobado = todosSubidos && todosAprobados;

        let nuevoEstadoLegajo = selectedStudent.estado_general;
        if (todoAprobado) {
          nuevoEstadoLegajo = 'aprobado';
        } else if (updatedDocs.some(d => d.estado === 'observado')) {
          nuevoEstadoLegajo = 'observado';
        } else if (todosSubidos) {
          nuevoEstadoLegajo = 'pendiente';
        } else {
          nuevoEstadoLegajo = 'incompleto';
        }
        
        setSelectedStudent({
          ...selectedStudent,
          estado_general: nuevoEstadoLegajo,
          documentos: updatedDocs
        });
        
        // Actualizar preview activo
        if (activeDocPreview && activeDocPreview.id === docId) {
          setActiveDocPreview({ ...activeDocPreview, estado: 'aprobado', observacion: null });
        }
      }
      
      await cargarLegajos(false);
    } catch {
      setError('No se pudo aprobar el documento.');
    } finally {
      setVerificandoLoading(false);
    }
  }, [selectedStudent, activeDocPreview]);

  // Rechazar un documento (abre modal)
  const handleRechazarClick = useCallback((doc) => {
    setDocToRechazar(doc);
    setMensajeRechazo('');
    setShowRechazoModal(true);
  }, []);

  const handleConfirmRechazo = useCallback(async () => {
    if (!mensajeRechazo) return;
    
    setVerificandoLoading(true);
    setShowRechazoModal(false);
    setError('');
    
    try {
      await adminAPI.rechazarDocumento(docToRechazar.id, mensajeRechazo);
      
      // Actualizar localmente
      if (selectedStudent) {
        const updatedDocs = selectedStudent.documentos.map(d => {
          if (d.id === docToRechazar.id) {
            return { ...d, estado: 'observado', observacion: mensajeRechazo };
          }
          return d;
        });
        
        setSelectedStudent({
          ...selectedStudent,
          estado_general: 'observado',
          documentos: updatedDocs
        });
        
        // Actualizar preview activo
        if (activeDocPreview && activeDocPreview.id === docToRechazar.id) {
          setActiveDocPreview({ ...activeDocPreview, estado: 'observado', observacion: mensajeRechazo });
        }
      }
      
      setDocToRechazar(null);
      setMensajeRechazo('');
      await cargarLegajos(false);
    } catch {
      setError('No se pudo guardar la observación del documento.');
    } finally {
      setVerificandoLoading(false);
    }
  }, [docToRechazar, mensajeRechazo, selectedStudent, activeDocPreview]);

  // Enviar observación masiva
  const handleEnviarObservacion = useCallback(async () => {
    if (!obsMensaje.trim()) return;
    if (obsDestino === 'especifico' && !obsUsuarioId) return;

    setObsLoading(true);
    setObsResult(null);
    setError('');
    try {
      const res = await adminAPI.enviarObservacion(
        obsMensaje.trim(),
        obsDestino,
        obsDestino === 'especifico' ? parseInt(obsUsuarioId) : null
      );
      setObsResult(res);
      setObsMensaje('');
      setObsUsuarioId('');
      setObsBusqueda('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al enviar la observación.');
    } finally {
      setObsLoading(false);
    }
  }, [obsMensaje, obsDestino, obsUsuarioId]);

  // Registrar estudiante individual
  const handleRegistroIndividual = useCallback(async (e) => {
    e.preventDefault();
    if (!registroForm.dni || !registroForm.nombre || !registroForm.apellido || !registroForm.email || !registroForm.carrera) {
      setError('Por favor complete todos los campos obligatorios.');
      return;
    }
    setRegistroLoading(true);
    setRegistroResult(null);
    setError('');
    try {
      const res = await adminAPI.registrarEstudiante(registroForm);
      setRegistroResult(res);
      setRegistroForm({ dni: '', nombre: '', apellido: '', email: '', carrera: '', telefono: '', direccion: '', localidad: '', provincia: '', fecha_nacimiento: '' });
      await cargarLegajos(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al registrar el estudiante.');
    } finally {
      setRegistroLoading(false);
    }
  }, [registroForm]);

  const nombresDocumentos = {
    dni_frente: 'DNI Frente',
    dni_dorso: 'DNI Dorso',
    foto_4x4: 'Foto Carnet 4x4',
    analitico_secundario: 'Analítico Secundario',
    partida_nacimiento: 'Partida de Nacimiento',
    formulario_inscripcion: 'Formulario de Inscripción'
  };

  const fDni = (dni) => {
    if (dni && dni.length === 8) {
      return `${dni.slice(0, 2)}.${dni.slice(2, 5)}.${dni.slice(5)}`;
    }
    return dni;
  };

  const fDob = (dob) => {
    if (!dob) return '-';
    try {
      const parts = dob.split('-');
      if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
      }
    } catch {
      // ignorar formato inesperado: devolver el valor original
    }
    return dob;
  };

  const getBadgeEstado = (estado) => {
    switch (estado) {
      case 'aprobado':
        return <span className="badge badge-aprobado">Aprobado</span>;
      case 'observado':
        return <span className="badge badge-observado">Observado</span>;
      case 'pendiente':
        return <span className="badge badge-pendiente">Pendiente</span>;
      case 'incompleto':
        return <span className="badge badge-incompleto">Incompleto</span>;
      default:
        return <span className="badge badge-incompleto">{estado}</span>;
    }
  };

  // Obtener lista única de carreras para filtros (memoizada)
  const carrerasDisponibles = useMemo(
    () => Array.from(new Set(legajos.map(l => l.carrera).filter(Boolean))),
    [legajos]
  );

  return (
    <div className="layout-container">
      {/* NAVBAR */}
      <header className="navbar">
        <div className="navbar-brand">
          <GraduationCap size={28} />
          <span>UNdeC</span> Legajos Digitales 
          <span style={{ fontSize: '0.75rem', backgroundColor: 'var(--accent-glow)', color: 'var(--accent)', padding: '0.15rem 0.5rem', borderRadius: '4px', marginLeft: '0.5rem', textTransform: 'uppercase' }}>
            Panel Admin
          </span>
        </div>
        <div className="navbar-menu">
          <div className="navbar-user-info">
            <span className="navbar-user-name">{user.nombre} {user.apellido}</span>
            <span className="navbar-user-role">{user.rol}</span>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={onLogout} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <LogOut size={16} /> Salir
          </button>
        </div>
      </header>

      {/* DASHBOARD PRINCIPAL */}
      <div style={{ maxWidth: '1400px', margin: '0 auto', width: '100%', padding: '2rem' }}>
        
        {/* FILA DE ESTADÍSTICAS */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.25rem', marginBottom: '2rem' }}>
          <div className="card" style={{ padding: '1.25rem' }}>
            <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Total Preinscriptos</h4>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--primary)', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Users size={28} /> {stats.total}
            </div>
          </div>
          <div className="card" style={{ padding: '1.25rem' }}>
            <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Pendientes de Revisión</h4>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--info)', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Loader2 size={28} /> {stats.pendientes}
            </div>
          </div>
          <div className="card" style={{ padding: '1.25rem' }}>
            <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Legajos Completos</h4>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--success)', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileCheck size={28} /> {stats.aprobados}
            </div>
          </div>
          <div className="card" style={{ padding: '1.25rem' }}>
            <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Legajos Observados</h4>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--warning)', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileWarning size={28} /> {stats.observados}
            </div>
          </div>
        </div>

        {error && (
          <div className="alert alert-danger" style={{ marginBottom: '1.5rem' }}>
            <AlertCircle size={20} />
            <span>{error}</span>
          </div>
        )}

        {/* ACCIÓN IMPORTAR ESTUDIANTES */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)' }}>Control de Legajos Digitales</h2>
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button 
              className="btn btn-primary"
              onClick={() => { setShowRegistroModal(true); setRegistroResult(null); setRegistroForm({ dni: '', nombre: '', apellido: '', email: '', carrera: '', telefono: '', direccion: '', localidad: '', provincia: '', fecha_nacimiento: '' }); }}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
            >
              <Users size={18} />
              Registrar Alumno
            </button>
            <button 
              className="btn btn-primary"
              onClick={() => { setShowImportPanel(!showImportPanel); setImportResult(null); }}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
            >
              <FileSpreadsheet size={18} />
              {showImportPanel ? 'Ocultar Importación' : 'Importación Masiva'}
            </button>
            <button 
              className="btn btn-primary"
              onClick={() => { setShowObsModal(true); setObsResult(null); setObsMensaje(''); setObsDestino('todos'); setObsUsuarioId(''); setObsBusqueda(''); }}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', backgroundColor: 'var(--accent)', borderColor: 'var(--accent)' }}
            >
              <MessageSquare size={18} />
              Enviar Observación
            </button>
          </div>
        </div>

        {/* PANEL DE IMPORTACIÓN CSV/EXCEL */}
        {showImportPanel && (
          <div className="card animate-fade-in" style={{ marginBottom: '2rem', borderColor: 'var(--primary-light)' }}>
            <h3 className="card-title" style={{ fontSize: '1.15rem' }}><FileSpreadsheet size={20} /> Carga Masiva de Preinscriptos</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
              Suba una base de datos en formato **CSV** o **Excel (.xlsx, .xls)**. Las columnas obligatorias requeridas son: <strong>nombre, apellido, dni, email, carrera</strong>. La sede se asigna automáticamente como "Sede Los Sarmientos".
            </p>

            <form onSubmit={handleImportSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="drag-drop-zone">
                <UploadCloud size={40} style={{ color: 'var(--primary-light)' }} />
                <div>
                  <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
                    Seleccionar Archivo
                    <input 
                      type="file" 
                      style={{ display: 'none' }}
                      accept=".csv, .xlsx, .xls"
                      onChange={(e) => setImportFile(e.target.files[0])}
                      required
                    />
                  </label>
                  {importFile && (
                    <div style={{ marginTop: '0.5rem', fontWeight: 600, fontSize: '0.85rem', color: 'var(--primary)' }}>
                      Archivo cargado: {importFile.name} ({(importFile.size / 1024).toFixed(1)} KB)
                    </div>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button type="button" className="btn btn-secondary" onClick={() => { setShowImportPanel(false); setImportFile(null); }}>
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary" disabled={importLoading || !importFile}>
                  {importLoading ? <div className="spinner" /> : 'Procesar e Importar Alumnos'}
                </button>
              </div>
            </form>

            {importResult && (
              <div style={{ marginTop: '1.5rem', padding: '1rem', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-main)', border: '1px solid var(--border-color)' }}>
                <h4 style={{ fontSize: '0.9rem', color: 'var(--primary)', marginBottom: '0.5rem' }}>Resumen de Importación</h4>
                <div style={{ fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <div>Total de Estudiantes Creados: <strong>{importResult.creados}</strong></div>
                  {importResult.errores && importResult.errores.length > 0 && (
                    <div style={{ marginTop: '0.5rem' }}>
                      <div style={{ color: 'var(--error)', fontWeight: 600, marginBottom: '0.25rem' }}>Detalle de Inconsistencias ({importResult.errores.length}):</div>
                      <div style={{ maxHeight: '150px', overflowY: 'auto', backgroundColor: '#fff', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '0.5rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {importResult.errores.map((err, idx) => (
                          <div key={idx} style={{ padding: '0.2rem 0', borderBottom: '1px solid #f1f5f9' }}>{err}</div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* COMPONENTE PRINCIPAL: TABLA + DETALLE SPLIT SCREEN */}
        <div style={{ display: 'grid', gridTemplateColumns: selectedStudent ? '1fr 1fr' : '1fr', gap: '1.5rem', alignItems: 'start' }}>
          
          {/* COLUMNA 1: LISTADO DE LEGAJOS */}
          <div className="card" style={{ padding: '1.5rem', overflowX: 'auto' }}>
            <h3 className="card-title" style={{ fontSize: '1.15rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span><Users size={20} /> Estudiantes Preinscriptos ({legajos.length})</span>
              <button 
                className="btn btn-secondary btn-sm" 
                onClick={() => cargarLegajos(true)}
                disabled={refreshing}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.3rem 0.6rem' }}
              >
                <RefreshCw size={12} style={refreshing ? { animation: 'spin 1s linear infinite' } : {}} /> {refreshing ? 'Actualizando...' : 'Refrescar'}
              </button>
            </h3>
            
            {/* FILTROS */}
            <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '0.75rem', margin: '1rem 0 1.5rem 0', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: '180px', position: 'relative' }}>
                <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input 
                  type="text" 
                  className="form-control" 
                  style={{ paddingLeft: '2.5rem' }} 
                  placeholder="Buscar por DNI o Nombre..."
                  value={filtroQuery}
                  onChange={handleQueryChange}
                />
              </div>

              <select 
                className="form-control form-select" 
                style={{ width: '180px' }}
                value={filtroCarrera}
                onChange={(e) => setFiltroCarrera(e.target.value)}
              >
                <option value="">Todas las Carreras</option>
                {carrerasDisponibles.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>

              <select 
                className="form-control form-select" 
                style={{ width: '150px' }}
                value={filtroEstado}
                onChange={(e) => setFiltroEstado(e.target.value)}
              >
                <option value="">Todos los Estados</option>
                <option value="pendiente">Pendientes</option>
                <option value="aprobado">Aprobados</option>
                <option value="observado">Observados</option>
                <option value="incompleto">Incompletos</option>
              </select>

              <button type="submit" className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <Filter size={16} /> Filtrar
              </button>
            </form>

            {/* TABLA */}
            {loading && legajos.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
                <Loader2 className="spinner spinner-primary" style={{ margin: '0 auto 1rem auto' }} />
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Buscando legajos en la base de datos...</p>
              </div>
            ) : legajos.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-muted)' }}>
                <AlertCircle size={36} style={{ color: 'var(--text-muted)', marginBottom: '0.5rem' }} />
                <p style={{ fontWeight: 600 }}>No se encontraron estudiantes cargados</p>
                <p style={{ fontSize: '0.8rem' }}>Intente importar un CSV o cambiar los parámetros de búsqueda.</p>
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--border-color)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Estudiante</th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Carrera</th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Documentos</th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Estado Legajo</th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {legajos.map((legajo) => {
                    const isSelected = selectedStudent?.usuario_id === legajo.usuario_id;
                    return (
                      <tr 
                        key={legajo.usuario_id} 
                        style={{ 
                          borderBottom: '1px solid var(--border-color)',
                          backgroundColor: isSelected ? 'var(--primary-glow)' : 'transparent',
                          transition: 'background var(--transition-fast)'
                        }}
                      >
                        <td style={{ padding: '0.75rem 0.5rem' }}>
                          <span style={{ fontWeight: 700, display: 'block', color: 'var(--primary)' }}>
                            {legajo.apellido}, {legajo.nombre}
                          </span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            DNI: {fDni(legajo.dni)}
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem', color: 'var(--text-main)', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {legajo.carrera}
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem', fontWeight: 600, color: 'var(--primary-light)' }}>
                          {legajo.total_documentos}/6 subidos
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem' }}>
                          {getBadgeEstado(legajo.estado_general)}
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>
                          <button 
                            className="btn btn-secondary btn-sm"
                            style={{ padding: '0.3rem 0.6rem', display: 'inline-flex', alignItems: 'center', gap: '0.2rem' }}
                            onClick={() => {
                              setSelectedStudent(legajo);
                              setActiveDocPreview(null);
                            }}
                          >
                            <Eye size={12} /> Revisar
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* COLUMNA 2: PANEL DE VERIFICACIÓN DETALLADA (SPLIT SCREEN) */}
          {selectedStudent && (
            <div className="card animate-fade-in" style={{ padding: '1.5rem', border: '1px solid var(--primary-light)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem' }}>
                <div>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--primary)' }}>
                    Verificación de Legajo
                  </h3>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                    Estudiante: <strong>{selectedStudent.nombre} {selectedStudent.apellido}</strong> (DNI: {fDni(selectedStudent.dni)})
                  </p>
                </div>
                <button 
                  className="btn btn-secondary btn-sm"
                  style={{ minWidth: 'auto', padding: '0.25rem' }}
                  onClick={() => { setSelectedStudent(null); setActiveDocPreview(null); }}
                >
                  <X size={18} />
                </button>
              </div>

              {/* DATOS PERSONALES DEL ESTUDIANTE */}
              <div style={{ backgroundColor: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '0.75rem', marginBottom: '1.25rem', fontSize: '0.8rem' }}>
                <h4 style={{ fontSize: '0.85rem', color: 'var(--primary)', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <Users size={14} /> Ficha Declarada por Estudiante
                </h4>
                {selectedStudent.tiene_datos_personales ? (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem 1rem' }}>
                    <div>Teléfono: <strong>{selectedStudent.datos_personales.telefono}</strong></div>
                    <div>Localidad: <strong>{selectedStudent.datos_personales.localidad}</strong></div>
                    <div>Dirección: <strong>{selectedStudent.datos_personales.direccion}</strong></div>
                    <div>Provincia: <strong>{selectedStudent.datos_personales.provincia}</strong></div>
                    <div>Fecha Nac: <strong>{fDob(selectedStudent.datos_personales.fecha_nacimiento)}</strong></div>
                    <div>Título: <strong>{selectedStudent.datos_personales.titulo_secundario}</strong></div>
                  </div>
                ) : (
                  <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>El estudiante no ha completado su formulario de datos personales todavía.</span>
                )}
              </div>

              {/* LISTA DE DOCUMENTOS CARGADOS */}
              <div style={{ marginBottom: '1.25rem' }}>
                <h4 style={{ fontSize: '0.85rem', color: 'var(--primary)', marginBottom: '0.5rem' }}>Documentación Cargada</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {selectedStudent.documentos.map((doc) => {
                    const isPreviewed = activeDocPreview?.id === doc.id;
                    return (
                      <div 
                        key={doc.id} 
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '0.5rem 0.75rem',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--border-color)',
                          backgroundColor: isPreviewed ? 'var(--primary-glow)' : 'white'
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          {getBadgeEstado(doc.estado)}
                          <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{nombresDocumentos[doc.tipo_documento]}</span>
                        </div>
                        <div style={{ display: 'flex', gap: '0.4rem' }}>
                          <button 
                            className="btn btn-secondary btn-sm"
                            style={{ padding: '0.2rem 0.4rem' }}
                            onClick={() => {
                              setActiveDocPreview(doc);
                            }}
                          >
                            <Eye size={12} /> Previsualizar
                          </button>
                        </div>
                      </div>
                    );
                  })}
                  {selectedStudent.documentos.length === 0 && (
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '1rem' }}>
                      Sin documentos cargados por el momento.
                    </div>
                  )}
                </div>
              </div>

              {/* PREVISUALIZADOR Y ASISTENTE OCR */}
              {activeDocPreview && (
                <div className="animate-fade-in" style={{ borderTop: '2px solid var(--border-color)', paddingTop: '1.25rem' }}>
                  <h4 style={{ fontSize: '0.9rem', color: 'var(--primary)', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Info size={16} /> Previsualización: {nombresDocumentos[activeDocPreview.tipo_documento]}
                  </h4>

                  {/* VISUALIZADOR DE ARCHIVO */}
                  <div style={{ 
                    width: '100%', 
                    height: '240px', 
                    border: '1px solid var(--border-color)', 
                    borderRadius: 'var(--radius-md)', 
                    overflow: 'hidden', 
                    backgroundColor: '#f1f5f9',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '1rem'
                  }}>
                    {activeDocPreview.archivo_url.toLowerCase().endsWith('.pdf') ? (
                      <div style={{ textAlign: 'center', padding: '1rem' }}>
                        <FileText size={48} style={{ color: 'var(--text-muted)', margin: '0 auto 0.5rem auto' }} />
                        <p style={{ fontSize: '0.8rem', fontWeight: 600 }}>Archivo en Formato PDF</p>
                        <a 
                          href={getFileUrl(activeDocPreview.archivo_url)} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="btn btn-secondary btn-sm"
                          style={{ marginTop: '0.5rem' }}
                        >
                          Abrir PDF en pestaña nueva
                        </a>
                      </div>
                    ) : (
                      <img 
                        src={getFileUrl(activeDocPreview.archivo_url)} 
                        alt={nombresDocumentos[activeDocPreview.tipo_documento]} 
                        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
                      />
                    )}
                  </div>

                  {/* NOTA: la validación OCR del DNI se realiza automáticamente al cargarlo */}
                  {activeDocPreview.tipo_documento === 'dni_frente' && (
                    <div style={{ backgroundColor: 'var(--primary-glow)', border: '1px solid var(--primary-light)', borderRadius: 'var(--radius-md)', padding: '0.75rem', marginBottom: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      <Sparkles size={14} style={{ color: 'var(--accent)' }} />
                      {' '}La coincidencia de los datos del DNI (número, nombre, apellido y fecha de nacimiento) se validó automáticamente con OCR al momento de cargar el documento, contrastándola contra la ficha declarada por el estudiante.
                    </div>
                  )}

                  {/* ACCIONES DE APROBACIÓN O RECHAZO DEL DOCUMENTO */}
                  <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                    {activeDocPreview.estado !== 'aprobado' && (
                      <button 
                        className="btn btn-secondary btn-sm"
                        style={{ color: 'var(--error)', borderColor: 'var(--error-border)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                        onClick={() => handleRechazarClick(activeDocPreview)}
                        disabled={verificandoLoading}
                      >
                        <X size={14} /> Observar Documento
                      </button>
                    )}
                    
                    <button 
                      className="btn btn-primary btn-sm"
                      style={{ backgroundColor: 'var(--success)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                      onClick={() => handleAprobarDoc(activeDocPreview.id)}
                      disabled={verificandoLoading || activeDocPreview.estado === 'aprobado'}
                    >
                      {verificandoLoading ? <div className="spinner" /> : (
                        <>
                          <Check size={14} /> 
                          {activeDocPreview.estado === 'aprobado' ? 'Documento Aprobado' : 'Aprobar Documento'}
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* MODAL PARA OBSERVACIÓN MASIVA */}
      {showObsModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '1rem',
          backdropFilter: 'blur(4px)'
        }}>
          <div className="card animate-fade-in-up" style={{ maxWidth: '560px', width: '100%', padding: '2rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '1.15rem', color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <MessageSquare size={20} /> Enviar Observación General
              </h3>
              <button className="btn btn-secondary btn-sm" style={{ padding: '0.25rem' }} onClick={() => setShowObsModal(false)}>
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Envíe un mensaje o comunicacion a uno o más estudiantes. Recibirán un correo electrónico notificándolos.
            </p>

            {/* Selector de destino */}
            <div className="form-group">
              <label className="form-label">¿A quién desea enviar la observación? *</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
                {[
                  { value: 'todos', label: 'Todos los estudiantes', desc: 'Envía a todos los estudiantes activos del sistema' },
                  { value: 'deudores', label: 'Estudiantes que deben documentación', desc: 'Solo a quienes les faltan documentos o tienen legajo observado' },
                  { value: 'especifico', label: 'Un estudiante en específico', desc: 'Seleccionar un estudiante de la lista' },
                ].map(opt => (
                  <label
                    key={opt.value}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '0.75rem',
                      padding: '0.6rem 0.75rem',
                      borderRadius: 'var(--radius-md)',
                      border: `1px solid ${obsDestino === opt.value ? 'var(--primary)' : 'var(--border-color)'}`,
                      backgroundColor: obsDestino === opt.value ? 'var(--primary-glow)' : 'white',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease'
                    }}
                  >
                    <input
                      type="radio"
                      name="obs-destino"
                      value={opt.value}
                      checked={obsDestino === opt.value}
                      onChange={(e) => setObsDestino(e.target.value)}
                      style={{ marginTop: '3px', accentColor: 'var(--primary)' }}
                    />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--primary)' }}>{opt.label}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{opt.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* Selector de estudiante específico con buscador */}
            {obsDestino === 'especifico' && (
              <div className="form-group animate-fade-in" style={{ marginTop: '1rem' }}>
                <label className="form-label" htmlFor="obs-estudiante">Buscar Estudiante por nombre o DNI *</label>
                <div style={{ position: 'relative' }}>
                  <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
                  <input
                    id="obs-estudiante"
                    type="text"
                    className="form-control"
                    style={{ paddingLeft: '2.5rem' }}
                    placeholder="Escribí el nombre, apellido o DNI del alumno..."
                    value={obsBusqueda}
                    onChange={(e) => {
                      setObsBusqueda(e.target.value);
                      setObsUsuarioId('');
                    }}
                  />
                </div>
                {obsBusqueda.trim() && (
                  <div style={{
                    maxHeight: '180px',
                    overflowY: 'auto',
                    border: '1px solid var(--border-color)',
                    borderRadius: 'var(--radius-md)',
                    marginTop: '0.5rem',
                    backgroundColor: 'white'
                  }}>
                    {legajos
                      .filter(l => {
                        const term = obsBusqueda.toLowerCase();
                        return (
                          l.nombre.toLowerCase().includes(term) ||
                          l.apellido.toLowerCase().includes(term) ||
                          l.dni.includes(term)
                        );
                      })
                      .slice(0, 15)
                      .map(l => (
                        <div
                          key={l.usuario_id}
                          onClick={() => {
                            setObsUsuarioId(String(l.usuario_id));
                            setObsBusqueda(`${l.apellido}, ${l.nombre} (DNI: ${l.dni})`);
                          }}
                          style={{
                            padding: '0.6rem 0.75rem',
                            cursor: 'pointer',
                            borderBottom: '1px solid var(--border-color)',
                            backgroundColor: obsUsuarioId === String(l.usuario_id) ? 'var(--primary-glow)' : 'transparent',
                            fontSize: '0.85rem',
                            transition: 'background 0.15s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--primary-glow)'}
                          onMouseLeave={(e) => { if (obsUsuarioId !== String(l.usuario_id)) e.currentTarget.style.backgroundColor = 'transparent'; }}
                        >
                          <span style={{ fontWeight: 700, color: 'var(--primary)' }}>{l.apellido}, {l.nombre}</span>
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '0.5rem' }}>DNI: {l.dni}</span>
                        </div>
                      ))}
                    {legajos.filter(l => {
                      const term = obsBusqueda.toLowerCase();
                      return (
                        l.nombre.toLowerCase().includes(term) ||
                        l.apellido.toLowerCase().includes(term) ||
                        l.dni.includes(term)
                      );
                    }).length === 0 && (
                      <div style={{ padding: '0.75rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem', fontStyle: 'italic' }}>
                        No se encontraron estudiantes con ese criterio
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Campo de mensaje */}
            <div className="form-group" style={{ marginTop: '1rem' }}>
              <label className="form-label" htmlFor="obs-mensaje">Mensaje / Observación *</label>
              <textarea
                id="obs-mensaje"
                className="form-control"
                rows="4"
                placeholder="Ej: Estimados estudiantes, les recordamos que la fecha límite para subir la documentación es el 30 de septiembre..."
                value={obsMensaje}
                onChange={(e) => setObsMensaje(e.target.value)}
              />
            </div>

            {/* Resultado del envío */}
            {obsResult && (
              <div className="alert alert-success" style={{ marginTop: '1rem' }}>
                <Check size={18} style={{ flexShrink: 0 }} />
                <span>{obsResult.message}</span>
              </div>
            )}

            {/* Acciones */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.25rem' }}>
              <button className="btn btn-secondary" onClick={() => setShowObsModal(false)}>
                Cancelar
              </button>
              <button
                className="btn btn-primary"
                onClick={handleEnviarObservacion}
                disabled={obsLoading || !obsMensaje.trim() || (obsDestino === 'especifico' && !obsUsuarioId)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                {obsLoading ? <div className="spinner" /> : <><Send size={16} /> Enviar Observación</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL PARA OBSERVACIONES/RECHAZO */}
      {showRechazoModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '1rem',
          backdropFilter: 'blur(4px)'
        }}>
          <div className="card animate-fade-in-up" style={{ maxWidth: '480px', width: '100%', padding: '2rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '1.15rem', color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <AlertCircle size={20} style={{ color: 'var(--warning)' }} /> Observar Documentación
              </h3>
              <button className="btn btn-secondary btn-sm" style={{ padding: '0.25rem' }} onClick={() => setShowRechazoModal(false)}>
                <X size={18} />
              </button>
            </div>
            
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Indique el motivo por el cual el documento <strong>{nombresDocumentos[docToRechazar?.tipo_documento]}</strong> es observado. El alumno recibirá una notificación de correo automático.
            </p>

            <div className="form-group">
              <label className="form-label" htmlFor="mensaje-obs">Mensaje de Observación *</label>
              <textarea 
                id="mensaje-obs" 
                className="form-control" 
                rows="4"
                placeholder="Ej: La imagen del DNI dorso se encuentra borrosa. Por favor, suba una foto nítida."
                value={mensajeRechazo}
                onChange={(e) => setMensajeRechazo(e.target.value)}
                required
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
              <button className="btn btn-secondary" onClick={() => setShowRechazoModal(false)}>
                Cancelar
              </button>
              <button 
                className="btn btn-danger" 
                onClick={handleConfirmRechazo}
                disabled={!mensajeRechazo}
              >
                Confirmar y Notificar Estudiante
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL PARA REGISTRO INDIVIDUAL DE ALUMNO */}
      {showRegistroModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '1rem',
          backdropFilter: 'blur(4px)'
        }}>
          <div className="card animate-fade-in-up" style={{ maxWidth: '600px', width: '100%', padding: '2rem', maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '1.15rem', color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Users size={20} /> Registrar Alumno Individual
              </h3>
              <button className="btn btn-secondary btn-sm" style={{ padding: '0.25rem' }} onClick={() => setShowRegistroModal(false)}>
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Complete los datos del estudiante. La contraseña por defecto será su número de DNI. Se enviará un correo de notificación con los datos de acceso.
            </p>

            {registroResult && (
              <div className="alert alert-success" style={{ marginBottom: '1rem' }}>
                <Check size={18} style={{ flexShrink: 0 }} />
                <span>{registroResult.message}</span>
              </div>
            )}

            <form onSubmit={handleRegistroIndividual}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label" htmlFor="reg-dni">DNI (sin puntos) *</label>
                  <input id="reg-dni" type="text" className="form-control" value={registroForm.dni} onChange={(e) => setRegistroForm({ ...registroForm, dni: e.target.value.replace(/\D/g, '') })} placeholder="Ej: 45123456" required />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-nombre">Nombre *</label>
                  <input id="reg-nombre" type="text" className="form-control" value={registroForm.nombre} onChange={(e) => setRegistroForm({ ...registroForm, nombre: e.target.value })} placeholder="Ej: Juan" required />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-apellido">Apellido *</label>
                  <input id="reg-apellido" type="text" className="form-control" value={registroForm.apellido} onChange={(e) => setRegistroForm({ ...registroForm, apellido: e.target.value })} placeholder="Ej: Perez" required />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label" htmlFor="reg-email">Correo Electrónico *</label>
                  <input id="reg-email" type="email" className="form-control" value={registroForm.email} onChange={(e) => setRegistroForm({ ...registroForm, email: e.target.value })} placeholder="Ej: juan.perez@correo.com" required />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label" htmlFor="reg-carrera">Carrera *</label>
                  <select id="reg-carrera" className="form-control form-select" value={registroForm.carrera} onChange={(e) => setRegistroForm({ ...registroForm, carrera: e.target.value })} required>
                    <option value="">Seleccione carrera</option>
                    <option value="Ingenieria en Sistemas">Ingenieria en Sistemas</option>
                    <option value="Licenciatura en Educacion">Licenciatura en Educacion</option>
                    <option value="Abogacia">Abogacia</option>
                    <option value="Sommelier">Sommelier</option>
                    <option value="Licenciatura en Turismo">Licenciatura en Turismo</option>
                    <option value="Licenciatura en Administracion">Licenciatura en Administracion</option>
                  </select>
                </div>
              </div>

              <hr style={{ border: 'none', borderTop: '1px solid var(--border-color)', margin: '1.25rem 0' }} />
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem', fontStyle: 'italic' }}>
                Los campos siguientes son opcionales. El estudiante podrá completarlos después desde su panel.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-telefono">Teléfono</label>
                  <input id="reg-telefono" type="tel" className="form-control" value={registroForm.telefono} onChange={(e) => setRegistroForm({ ...registroForm, telefono: e.target.value })} placeholder="Ej: 3825123456" />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-fecha-nac">Fecha de Nacimiento</label>
                  <input id="reg-fecha-nac" type="date" className="form-control" value={registroForm.fecha_nacimiento} onChange={(e) => setRegistroForm({ ...registroForm, fecha_nacimiento: e.target.value })} />
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label" htmlFor="reg-direccion">Domicilio</label>
                  <input id="reg-direccion" type="text" className="form-control" value={registroForm.direccion} onChange={(e) => setRegistroForm({ ...registroForm, direccion: e.target.value })} placeholder="Ej: Av. Principal 123" />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-localidad">Localidad</label>
                  <input id="reg-localidad" type="text" className="form-control" value={registroForm.localidad} onChange={(e) => setRegistroForm({ ...registroForm, localidad: e.target.value })} placeholder="Ej: Chilecito" />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-provincia">Provincia</label>
                  <input id="reg-provincia" type="text" className="form-control" value={registroForm.provincia} onChange={(e) => setRegistroForm({ ...registroForm, provincia: e.target.value })} placeholder="Ej: La Rioja" />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowRegistroModal(false)}>
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary" disabled={registroLoading} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  {registroLoading ? <div className="spinner" /> : <><Check size={16} /> Registrar Alumno</>}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
