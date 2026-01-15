import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Activity, Cpu, HardDrive } from 'lucide-react';

interface ServiceStatus {
  id: string;
  name: string;
  port: number;
  status: 'running' | 'stopped';
  pid: number | null;
  ram_gb: number;
  vram_gb: number;
  cpu_percent: number;
}

interface SystemStatusData {
  services: ServiceStatus[];
  system: {
    total_ram_gb: number;
    total_vram_gb: number;
    ram_used_gb: number;
    cpu_percent: number;
  };
}

export default function SystemStatus() {
  const [data, setData] = useState<SystemStatusData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const status = await api.getSystemStatus() as any;
      setData(status);
    } catch (error) {
      console.error('Error fetching system status:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Poll every 5 seconds for system status (no WebSocket events for this)
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !data) {
    return <div className="p-4 text-center text-gray-500">Loading system status...</div>;
  }

  if (!data) return null;

  return (
    <div className="bg-white rounded border border-gray-200 overflow-hidden">
      <div className="p-4 border-b border-gray-100 bg-gray-50">
        <h3 className="font-semibold text-gray-800 flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary-600" />
          System Monitor
        </h3>
      </div>
      
      {/* System Overview */}
      <div className="grid grid-cols-2 gap-4 p-4 border-b border-gray-100">
        <div>
          <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
            <Cpu className="w-3 h-3" /> System RAM
          </div>
          <div className="h-2 bg-gray-100 rounded overflow-hidden">
            <div 
              className="h-full bg-blue-500 transition-all duration-500"
              style={{ width: `${(data.system.ram_used_gb / data.system.total_ram_gb) * 100}%` }}
            />
          </div>
          <div className="text-xs text-gray-600 mt-1">
            {data.system.ram_used_gb.toFixed(1)} / {data.system.total_ram_gb.toFixed(1)} GB
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
            <HardDrive className="w-3 h-3" /> System VRAM
          </div>
          <div className="h-2 bg-gray-100 rounded overflow-hidden">
            <div 
              className="h-full bg-purple-500 transition-all duration-500"
              style={{ width: `${(data.system.total_vram_gb > 0 ? (data.system.total_vram_gb - (data.system.total_vram_gb - data.services.reduce((acc, s) => acc + s.vram_gb, 0))) / data.system.total_vram_gb : 0) * 100}%` }}
            />
          </div>
          <div className="text-xs text-gray-600 mt-1">
            {data.system.total_vram_gb > 0 ? `${data.system.total_vram_gb.toFixed(1)} GB Total` : 'N/A'}
          </div>
        </div>
      </div>

      {/* Services List */}
      <div className="divide-y divide-gray-100">
        {data.services.map((service) => (
          <div key={service.id} className="p-3 hover:bg-gray-50 transition-colors">
            <div className="flex justify-between items-center mb-2">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded ${service.status === 'running' ? 'bg-green-500' : 'bg-gray-300'}`} />
                <span className="text-sm font-medium text-gray-700">{service.name}</span>
              </div>
              {service.status === 'running' && (
                <span className="text-xs text-gray-400">PID: {service.pid}</span>
              )}
            </div>
            
            {service.status === 'running' && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-500">RAM</span>
                    <span className="text-gray-700 font-medium">{service.ram_gb.toFixed(2)} GB</span>
                  </div>
                  <div className="h-1.5 bg-gray-100 rounded overflow-hidden">
                    <div 
                      className="h-full bg-blue-500/70"
                      style={{ width: `${Math.min((service.ram_gb / data.system.total_ram_gb) * 100, 100)}%` }}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-500">VRAM</span>
                    <span className="text-gray-700 font-medium">{service.vram_gb.toFixed(2)} GB</span>
                  </div>
                  <div className="h-1.5 bg-gray-100 rounded overflow-hidden">
                    <div 
                      className="h-full bg-purple-500/70"
                      style={{ width: `${data.system.total_vram_gb > 0 ? Math.min((service.vram_gb / data.system.total_vram_gb) * 100, 100) : 0}%` }}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
