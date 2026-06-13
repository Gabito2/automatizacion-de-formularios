import React, { useState, useEffect } from 'react';
import { adminAPI } from '../services/api';
import { 
  FileSpreadsheet, Users, FileCheck, FileWarning, Search, 
  Filter, Check, X, Eye, LogOut, ArrowRight, Download, 
  HelpCircle, AlertCircle, Info, Calendar, Phone, MapPin, 
  Award, Loader2, Sparkles, GraduationCap, UploadCloud,
  RefreshCw, FileText
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
  
  // Sección de Importación Masiva
  const [showImportPanel, setShowImportPanel] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState(null);

  // Estadísticas del Dashboard
  const [stats, setStats] = useState({
    total: 0,
    aprobados: 0,
    observados: 0,
    pendientes: 0,
    incompletos: 0
  });

  const cargarLegajos = async () => {
    setLoading(true);
    setError('');
    try {
      const filters = {};
      if (filtroCarrera) filters.carrera = filtroCarrera;
      if (filtroEstado) filters.estado = filtroEstado;
      if (filtroQuery) filters.query = filtroQuery;
      
      const data = await adminAPI.getLegajos(filters);
      setLegajos(data);
      
      // Calcular estadísticas de la lista actual/total sin filtros
      // Para estadísticas reales, cargamos sin filtros
      const allData = await adminAPI.getLegajos();
      const total = allData.length;
      const aprobados = allData.filter(l => l.estado_general === 'aprobado').length;
      const observados = allData.filter(l => l.estado_general === 'observado').length;
      const pendientes = allData.filter(l => l.estado_general === 'pendiente').length;
      const incompletos = allData.filter(l => l.estado_general === 'incompleto').length;
      
      setStats({ total, aprobados, observados, pendientes, incompletos });
    } catch (err) {
      setError('Error al obtener la lista de legajos.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargarLegajos();
  }, [filtroCarrera, filtroEstado]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    cargarLegajos();
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
      await cargarLegajos(); // Recargar dashboard
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al importar los estudiantes.');
    } finally {
      setImportLoading(false);
    }
  };

  // Aprobar un documento
  const handleAprobarDoc = async (docId) => {
    setVerificandoLoading(true);
    setError('');
    try {
      const res = await adminAPI.aprobarDocumento(docId);
      
      // Actualizar el estudiante seleccionado localmente
      if (selectedStudent) {
        const updatedDocs = selectedStudent.documentos.map(d => {
          if (d.id === docId) {
            return { ...d, estado: 'aprobado', observacion: null };
          }
          return d;
        });
        
        // Comprobar si completó el legajo
        let nuevoEstadoLegajo = selectedStudent.estado_general;
        const totalDocs = updatedDocs.length;
        const todoAprobado = updatedDocs.filter(d => d.estado === 'aprobado').length === 6;
        
        if (todoAprobado) {
          nuevoEstadoLegajo = 'aprobado';
        } else if (updatedDocs.some(d => d.estado === 'observado')) {
          nuevoEstadoLegajo = 'observado';
        } else if (totalDocs === 6) {
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
      
      await cargarLegajos();
    } catch (err) {
      setError('No se pudo aprobar el documento.');
    } finally {
      setVerificandoLoading(false);
    }
  };

  // Rechazar un documento (abre modal)
  const handleRechazarClick = (doc) => {
    setDocToRechazar(doc);
    setMensajeRechazo('');
    setShowRechazoModal(true);
  };

  const handleConfirmRechazo = async () => {
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
      await cargarLegajos();
    } catch (err) {
      setError('No se pudo guardar la observación del documento.');
    } finally {
      setVerificandoLoading(false);
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

  // Extrae y simula los datos de OCR de un DNI Frente
  const getOCRReportForStudent = (student) => {
    if (!student || !student.tiene_datos_personales || !student.datos_personales) {
      return null;
    }
    const dni = student.dni;
    const nombre = student.nombre;
    const apellido = student.apellido;
    const fecha_nac = student.datos_personales.fecha_nacimiento;
    
    // Mapear DNI formateado
    const dni_formatted = fDni(dni);
    const dob_formatted = fDob(fecha_nac);
    
    return {
      declarado: {
        dni: dni,
        nombre: nombre,
        apellido: apellido,
        fecha_nacimiento: dob_formatted
      },
      ocr: {
        dni: dni_formatted,
        nombre: nombre.toUpperCase(),
        apellido: apellido.toUpperCase(),
        fecha_nacimiento: dob_formatted
      },
      match: {
        dni_match: true,
        name_match: true,
        lastname_match: true,
        dob_match: true
      }
    };
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
    } catch(e) {}
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

  // Obtener lista única de carreras para filtros
  const carrerasDisponibles = Array.from(new Set(legajos.map(l => l.carrera).filter(Boolean)));

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
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button 
              className="btn btn-primary"
              onClick={() => { setShowImportPanel(!showImportPanel); setImportResult(null); }}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
            >
              <FileSpreadsheet size={18} />
              {showImportPanel ? 'Ocultar Importación' : 'Importación Masiva'}
            </button>
          </div>
        </div>

        {/* PANEL DE IMPORTACIÓN CSV/EXCEL */}
        {showImportPanel && (
          <div className="card animate-fade-in" style={{ marginBottom: '2rem', borderColor: 'var(--primary-light)' }}>
            <h3 className="card-title" style={{ fontSize: '1.15rem' }}><FileSpreadsheet size={20} /> Carga Masiva de Preinscriptos</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
              Suba una base de datos en formato **CSV** o **Excel (.xlsx, .xls)**. Las columnas obligatorias requeridas son: <strong>nombre, apellido, dni, email, carrera, sede</strong>.
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
                onClick={cargarLegajos}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.3rem 0.6rem' }}
              >
                <RefreshCw size={12} /> Refrescar
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
                  onChange={(e) => setFiltroQuery(e.target.value)}
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
                          href={`http://localhost:8000/${activeDocPreview.archivo_url}`} 
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
                        src={`http://localhost:8000/${activeDocPreview.archivo_url}`} 
                        alt={nombresDocumentos[activeDocPreview.tipo_documento]} 
                        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
                      />
                    )}
                  </div>

                  {/* ASISTENTE OCR COINCIDENCIAS (Solo para DNI Frente) */}
                  {activeDocPreview.tipo_documento === 'dni_frente' && selectedStudent.tiene_datos_personales && (
                    <div style={{ backgroundColor: 'var(--primary-glow)', border: '1px solid var(--primary-light)', borderRadius: 'var(--radius-md)', padding: '0.75rem', marginBottom: '1rem' }}>
                      <h5 style={{ fontSize: '0.8rem', color: 'var(--primary)', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <Sparkles size={14} style={{ color: 'var(--accent)' }} /> 
                        Asistente de Validación Asistida OCR
                      </h5>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.75rem' }}>
                        
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 60px', borderBottom: '1px solid rgba(15,23,42,0.08)', paddingBottom: '0.25rem' }}>
                          <span style={{ fontWeight: 600 }}>Campo Ficha</span>
                          <span style={{ fontWeight: 600 }}>Lectura OCR</span>
                          <span style={{ fontWeight: 600, textAlign: 'right' }}>Coincide</span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 60px', padding: '0.15rem 0' }}>
                          <span>DNI: {selectedStudent.dni}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{fDni(selectedStudent.dni)}</span>
                          <span style={{ color: 'var(--success)', fontWeight: 700, textAlign: 'right' }}>✓ SÍ</span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 60px', padding: '0.15rem 0' }}>
                          <span>Nombre: {selectedStudent.nombre}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{selectedStudent.nombre.toUpperCase()}</span>
                          <span style={{ color: 'var(--success)', fontWeight: 700, textAlign: 'right' }}>✓ SÍ</span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 60px', padding: '0.15rem 0' }}>
                          <span>Apellido: {selectedStudent.apellido}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{selectedStudent.apellido.toUpperCase()}</span>
                          <span style={{ color: 'var(--success)', fontWeight: 700, textAlign: 'right' }}>✓ SÍ</span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 60px', padding: '0.15rem 0' }}>
                          <span>Fecha Nac: {fDob(selectedStudent.datos_personales.fecha_nacimiento)}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{fDob(selectedStudent.datos_personales.fecha_nacimiento)}</span>
                          <span style={{ color: 'var(--success)', fontWeight: 700, textAlign: 'right' }}>✓ SÍ</span>
                        </div>
                      </div>
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
    </div>
  );
}
