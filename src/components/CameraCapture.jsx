import { useRef, useState, useCallback, useEffect } from 'react';
import { Camera, X, RotateCcw, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

/**
 * CameraCapture — Componente modal de captura de cámara
 *
 * Props:
 *   - onCapture(blob, dataUrl): Callback con el Blob capturado y el dataURL base64
 *   - onClose(): Callback al cerrar sin capturar
 *   - title (string): Título del modal
 *   - hint (string): Texto de ayuda (ej: "Coloque el frente de su DNI centrado")
 */
export default function CameraCapture({ onCapture, onClose, title = 'Captura de Cámara', hint = '' }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  // Ref espejo del stream: el cleanup del efecto de montaje usa una closure con el
  // valor inicial (null) y de otro modo las pistas de cámara quedarían activas al desmontar.
  const streamRef = useRef(null);

  const [stream, setStream] = useState(null);
  const [captured, setCaptured] = useState(null);   // dataURL de la captura
  const [capturedBlob, setCapturedBlob] = useState(null);
  const [cameraError, setCameraError] = useState('');
  const [facingMode, setFacingMode] = useState('environment'); // 'environment' = trasera, 'user' = selfie
  const [starting, setStarting] = useState(true);

  const stopTracks = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
  };

  // Inicializar cámara
  const startCamera = useCallback(async (facing) => {
    setStarting(true);
    setCameraError('');

    // Detener stream anterior si existe
    stopTracks();
    setStream(null);

    try {
      const constraints = {
        video: {
          facingMode: { ideal: facing },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      };
      const newStream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = newStream;
      setStream(newStream);
      if (videoRef.current) {
        videoRef.current.srcObject = newStream;
      }
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setCameraError('No se otorgaron permisos de cámara. Por favor, habilite el acceso en la configuración de su navegador.');
      } else if (err.name === 'NotFoundError') {
        setCameraError('No se encontró una cámara disponible en este dispositivo.');
      } else {
        setCameraError(`Error al acceder a la cámara: ${err.message}`);
      }
    } finally {
      setStarting(false);
    }
  }, []);

  useEffect(() => {
    startCamera(facingMode);
    // Limpiar al desmontar
    return stopTracks;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- iniciar cámara solo al montar
  }, []);

  // Cambiar cámara (trasera ↔ delantera)
  const toggleCamera = async () => {
    const newFacing = facingMode === 'environment' ? 'user' : 'environment';
    setFacingMode(newFacing);
    setCaptured(null);
    setCapturedBlob(null);
    await startCamera(newFacing);
  };

  // Capturar frame actual
  const capturePhoto = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.92);
    setCaptured(dataUrl);
    canvas.toBlob(blob => setCapturedBlob(blob), 'image/jpeg', 0.92);
  };

  // Repetir captura
  const retake = () => {
    setCaptured(null);
    setCapturedBlob(null);
  };

  // Confirmar captura y cerrar
  const confirmCapture = () => {
    if (captured && capturedBlob) {
      onCapture(capturedBlob, captured);
      // Detener el stream
      if (stream) stream.getTracks().forEach(t => t.stop());
    }
  };

  // Cerrar sin capturar
  const handleClose = () => {
    if (stream) stream.getTracks().forEach(t => t.stop());
    onClose();
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.85)',
      zIndex: 9999,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '1rem',
    }}>
      <div style={{
        background: '#1a1a2e',
        borderRadius: '16px',
        width: '100%',
        maxWidth: '560px',
        boxShadow: '0 25px 60px rgba(0,0,0,0.7)',
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,0.1)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '1rem 1.25rem',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          background: 'linear-gradient(90deg, #0f3460, #16213e)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Camera size={20} color="#60a5fa" />
            <span style={{ color: '#fff', fontWeight: 700, fontSize: '1rem' }}>{title}</span>
          </div>
          <button
            onClick={handleClose}
            style={{
              background: 'rgba(255,255,255,0.1)',
              border: 'none',
              borderRadius: '50%',
              width: '32px',
              height: '32px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              transition: 'background 0.2s',
            }}
            title="Cerrar"
          >
            <X size={18} />
          </button>
        </div>

        {/* Hint */}
        {hint && (
          <div style={{
            background: 'rgba(96, 165, 250, 0.1)',
            borderBottom: '1px solid rgba(96, 165, 250, 0.2)',
            padding: '0.6rem 1.25rem',
            fontSize: '0.8rem',
            color: '#93c5fd',
            textAlign: 'center',
          }}>
            {hint}
          </div>
        )}

        {/* Área de cámara o captura */}
        <div style={{ position: 'relative', background: '#000', minHeight: '300px' }}>

          {/* Estado de cargando cámara */}
          {starting && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              color: '#93c5fd', gap: '0.75rem',
            }}>
              <Loader2 size={36} style={{ animation: 'spin 1s linear infinite' }} />
              <span style={{ fontSize: '0.85rem' }}>Iniciando cámara...</span>
            </div>
          )}

          {/* Error de cámara */}
          {cameraError && !starting && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              padding: '1.5rem', textAlign: 'center', gap: '0.75rem',
            }}>
              <AlertCircle size={40} color="#f87171" />
              <p style={{ color: '#fca5a5', fontSize: '0.85rem', maxWidth: '320px' }}>{cameraError}</p>
              <button
                onClick={() => startCamera(facingMode)}
                style={{
                  background: '#3b82f6', color: '#fff', border: 'none',
                  borderRadius: '8px', padding: '0.5rem 1.25rem',
                  cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600,
                }}
              >
                Reintentar
              </button>
            </div>
          )}

          {/* Video en vivo */}
          {!captured && !cameraError && (
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: '100%',
                display: 'block',
                maxHeight: '360px',
                objectFit: 'cover',
              }}
            />
          )}

          {/* Vista previa de la captura */}
          {captured && (
            <div style={{ position: 'relative' }}>
              <img
                src={captured}
                alt="Captura"
                style={{ width: '100%', display: 'block', maxHeight: '360px', objectFit: 'cover' }}
              />
              {/* Badge de captura exitosa */}
              <div style={{
                position: 'absolute',
                top: '0.75rem',
                left: '50%',
                transform: 'translateX(-50%)',
                background: 'rgba(34, 197, 94, 0.9)',
                color: '#fff',
                borderRadius: '999px',
                padding: '0.3rem 0.85rem',
                fontSize: '0.78rem',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                backdropFilter: 'blur(4px)',
              }}>
                <CheckCircle2 size={14} />
                Foto capturada
              </div>
            </div>
          )}

          {/* Canvas oculto para captura */}
          <canvas ref={canvasRef} style={{ display: 'none' }} />

          {/* Guía visual de encuadre (solo en vista en vivo, sin captura) */}
          {!captured && !cameraError && !starting && (
            <div style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              width: '75%',
              height: '70%',
              border: '2px dashed rgba(96,165,250,0.6)',
              borderRadius: '8px',
              pointerEvents: 'none',
            }} />
          )}
        </div>

        {/* Controles */}
        <div style={{
          padding: '1rem 1.25rem',
          background: '#16213e',
          display: 'flex',
          justifyContent: 'center',
          gap: '0.75rem',
          flexWrap: 'wrap',
        }}>
          {!captured ? (
            <>
              {/* Botón rotar cámara */}
              <button
                onClick={toggleCamera}
                disabled={starting || !!cameraError}
                title="Cambiar cámara (frontal/trasera)"
                style={{
                  background: 'rgba(255,255,255,0.1)',
                  border: '1px solid rgba(255,255,255,0.2)',
                  borderRadius: '50%',
                  width: '48px',
                  height: '48px',
                  cursor: starting || cameraError ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#93c5fd',
                  flexShrink: 0,
                }}
              >
                <RotateCcw size={20} />
              </button>

              {/* Botón de captura principal */}
              <button
                onClick={capturePhoto}
                disabled={starting || !!cameraError}
                style={{
                  background: starting || cameraError ? '#374151' : 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                  border: 'none',
                  borderRadius: '999px',
                  padding: '0.65rem 2rem',
                  cursor: starting || cameraError ? 'not-allowed' : 'pointer',
                  color: '#fff',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  boxShadow: starting || cameraError ? 'none' : '0 4px 15px rgba(59,130,246,0.4)',
                  transition: 'all 0.2s',
                }}
              >
                <Camera size={18} />
                Tomar Foto
              </button>
            </>
          ) : (
            <>
              {/* Repetir */}
              <button
                onClick={retake}
                style={{
                  background: 'rgba(255,255,255,0.1)',
                  border: '1px solid rgba(255,255,255,0.2)',
                  borderRadius: '8px',
                  padding: '0.65rem 1.25rem',
                  cursor: 'pointer',
                  color: '#d1d5db',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                }}
              >
                <RotateCcw size={16} />
                Repetir
              </button>

              {/* Usar foto */}
              <button
                onClick={confirmCapture}
                style={{
                  background: 'linear-gradient(135deg, #22c55e, #16a34a)',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '0.65rem 1.75rem',
                  cursor: 'pointer',
                  color: '#fff',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  boxShadow: '0 4px 15px rgba(34,197,94,0.35)',
                }}
              >
                <CheckCircle2 size={18} />
                Usar esta Foto
              </button>
            </>
          )}
        </div>
      </div>

      {/* Animación del spinner */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
