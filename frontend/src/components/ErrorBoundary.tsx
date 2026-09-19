// v0.9.15: Global ErrorBoundary — React tree crash olduğunda beyaz sayfa
// yerine hata mesajı + stack göster. Böylece bug'ın kök nedeni belli olur.
import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  info: string | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, info: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, info: null };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught:', error, info);
    this.setState({ info: info?.componentStack || null });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, info: null });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError && this.state.error) {
      return (
        <div style={{
          padding: '24px',
          fontFamily: 'system-ui, sans-serif',
          maxWidth: '900px',
          margin: '40px auto',
        }}>
          <div style={{
            background: '#fee',
            border: '1px solid #f99',
            borderLeft: '4px solid #c00',
            borderRadius: '6px',
            padding: '16px',
            marginBottom: '16px',
          }}>
            <h2 style={{ margin: '0 0 8px 0', color: '#900' }}>
              ⚠ Bir hata oluştu (React tree crash)
            </h2>
            <div style={{
              fontFamily: 'monospace',
              fontSize: '13px',
              background: '#fff',
              padding: '10px',
              borderRadius: '4px',
              overflow: 'auto',
              color: '#c00',
            }}>
              <b>{this.state.error.name}:</b> {this.state.error.message}
            </div>
            {this.state.error.stack && (
              <details style={{ marginTop: '10px' }}>
                <summary style={{ cursor: 'pointer', color: '#666' }}>
                  Stack trace (geliştirici için)
                </summary>
                <pre style={{
                  fontFamily: 'monospace',
                  fontSize: '11px',
                  background: '#fff',
                  padding: '10px',
                  borderRadius: '4px',
                  overflow: 'auto',
                  color: '#333',
                  maxHeight: '300px',
                  whiteSpace: 'pre-wrap',
                }}>
                  {this.state.error.stack}
                </pre>
              </details>
            )}
            {this.state.info && (
              <details style={{ marginTop: '10px' }}>
                <summary style={{ cursor: 'pointer', color: '#666' }}>
                  Component stack
                </summary>
                <pre style={{
                  fontFamily: 'monospace',
                  fontSize: '11px',
                  background: '#fff',
                  padding: '10px',
                  borderRadius: '4px',
                  overflow: 'auto',
                  color: '#333',
                  maxHeight: '300px',
                  whiteSpace: 'pre-wrap',
                }}>
                  {this.state.info}
                </pre>
              </details>
            )}
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              onClick={this.handleReset}
              style={{
                padding: '8px 14px',
                border: '1px solid #ccc',
                borderRadius: '4px',
                background: '#fff',
                cursor: 'pointer',
              }}
            >
              Tekrar dene
            </button>
            <button
              type="button"
              onClick={this.handleReload}
              style={{
                padding: '8px 14px',
                border: 'none',
                borderRadius: '4px',
                background: '#2563eb',
                color: '#fff',
                cursor: 'pointer',
              }}
            >
              Sayfayı yeniden yükle
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
