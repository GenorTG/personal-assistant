import React, { useState, useEffect } from 'react';
import { RefreshCw, Play, AlertCircle } from 'lucide-react';
import { api } from '../lib/api';

interface ServiceStatus {
  name: string;
  status: 'ready' | 'error' | 'initializing' | 'stopped';
  error_message?: string;
  is_current: boolean;
}

export const ServiceStatusPanel: React.FC = () => {
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchServices = async () => {
    setLoading(true);
    try {
      const backends = await api.getTTSBackends() as any[];
      // Map backend info to service status
      const mapped = backends.map((b: any) => ({
        name: b.name,
        status: b.status,
        error_message: b.error_message,
        is_current: b.is_current
      }));
      setServices(mapped);
    } catch (error) {
      console.error('Failed to fetch services:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchServices();
    const interval = setInterval(fetchServices, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleStartService = async (name: string) => {
    setActionLoading(name);
    try {
      await api.startTTSBackend(name);
      // Wait a bit for startup
      setTimeout(fetchServices, 2000);
    } catch (error) {
      console.error(`Failed to start ${name}:`, error);
    } finally {
      setActionLoading(null);
    }
  };

  const handleSwitch = async (name: string) => {
    setActionLoading(name);
    try {
      await api.setTTSBackend(name);
      fetchServices();
    } catch (error) {
      console.error(`Failed to switch to ${name}:`, error);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="bg-gray-800/50 rounded-xl p-6 border border-gray-700/50 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          Service Status
        </h2>
        <button 
          onClick={fetchServices}
          className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      <div className="space-y-4">
        {services.map((service) => (
          <div 
            key={service.name}
            className={`p-4 rounded-lg border transition-all ${
              service.is_current 
                ? 'bg-blue-500/10 border-blue-500/50' 
                : 'bg-gray-900/50 border-gray-700'
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full ${
                  service.status === 'ready' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' :
                  service.status === 'initializing' ? 'bg-yellow-500 animate-pulse' :
                  'bg-red-500'
                }`} />
                <div>
                  <h3 className="font-medium text-white capitalize">{service.name}</h3>
                  <p className="text-xs text-gray-400">
                    {service.status === 'ready' ? 'Running' : 
                     service.status === 'initializing' ? 'Starting...' : 
                     'Stopped / Error'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {service.status !== 'ready' && service.name === 'kokoro' && (
                  <button
                    onClick={() => handleStartService(service.name)}
                    disabled={!!actionLoading}
                    className="px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white text-sm rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50"
                  >
                    {actionLoading === service.name ? (
                      <RefreshCw className="w-3 h-3 animate-spin" />
                    ) : (
                      <Play className="w-3 h-3" />
                    )}
                    Start
                  </button>
                )}

                {!service.is_current && (
                  <button
                    onClick={() => handleSwitch(service.name)}
                    disabled={!!actionLoading}
                    className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
                  >
                    Switch To
                  </button>
                )}
              </div>
            </div>

            {service.error_message && (
              <div className="mt-3 flex items-start gap-2 text-xs text-red-400 bg-red-500/10 p-2 rounded">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <p>{service.error_message}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
