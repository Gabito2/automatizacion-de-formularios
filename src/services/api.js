import axios from 'axios';

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
});

// Interceptor para inyectar automáticamente el Token JWT
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export const authAPI = {
  login: async (dni, password) => {
    const response = await api.post('/auth/login', { dni, password });
    return response.data;
  },
  changePassword: async (oldPassword, newPassword) => {
    const response = await api.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    });
    return response.data;
  },
  recover: async (dni, email) => {
    const response = await api.post('/auth/recovery', { dni, email });
    return response.data;
  },
  register: async (formData) => {
    const response = await api.post('/auth/register', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  analizarDni: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/auth/analizar-dni', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  analizarFoto: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/auth/analizar-foto', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  /** Analiza DNI capturado desde cámara (envia base64 JSON) */
  analizarDniCamara: async (dataUrl, filename = 'camara.jpg') => {
    const response = await api.post('/auth/analizar-dni-camara', {
      image_base64: dataUrl,
      filename,
    });
    return response.data;
  },
  /** Analiza foto personal capturada desde cámara (envia base64 JSON) */
  analizarFotoCamara: async (dataUrl, filename = 'camara.jpg') => {
    const response = await api.post('/auth/analizar-foto-camara', {
      image_base64: dataUrl,
      filename,
    });
    return response.data;
  },
  /** Analiza un archivo compuesto (imagen o PDF) que puede contener múltiples documentos */
  analizarArchivoCompuesto: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/auth/analizar-archivo-compuesto', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};

export const estudianteAPI = {
  getPerfil: async () => {
    const response = await api.get('/estudiante/datos-personales');
    return response.data;
  },
  savePerfil: async (data) => {
    const response = await api.post('/estudiante/datos-personales', data);
    return response.data;
  },
  uploadDocumento: async (tipoDocumento, file) => {
    const formData = new FormData();
    formData.append('tipo_documento', tipoDocumento);
    formData.append('file', file);
    const response = await api.post('/estudiante/documentos', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  actualizarDatosDni: async (data) => {
    const response = await api.post('/estudiante/actualizar-datos-dni', data);
    return response.data;
  },
  getEstado: async () => {
    const response = await api.get('/estudiante/estado');
    return response.data;
  },
  /** Sube un documento capturado desde cámara (envia base64 JSON) */
  uploadDocumentoCamara: async (tipoDocumento, dataUrl, filename = 'camara.jpg') => {
    const response = await api.post('/estudiante/documentos-camara', {
      tipo_documento: tipoDocumento,
      image_base64: dataUrl,
      filename,
    });
    return response.data;
  },
};

export const adminAPI = {
  importarEstudiantes: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/admin/importar-estudiantes', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  getLegajos: async (filters = {}) => {
    const response = await api.get('/admin/legajos', { params: filters });
    return response.data;
  },
  aprobarDocumento: async (id) => {
    const response = await api.put(`/admin/documento/${id}/aprobar`);
    return response.data;
  },
  rechazarDocumento: async (id, mensaje) => {
    const response = await api.put(`/admin/documento/${id}/rechazar`, { mensaje });
    return response.data;
  },
};

export default api;
