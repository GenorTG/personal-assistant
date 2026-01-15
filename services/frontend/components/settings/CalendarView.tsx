'use client';

import { useState } from 'react';
import { Calendar as CalendarIcon, Plus, Trash2, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
// Date formatting utilities (using native JavaScript instead of date-fns)
const formatDate = (dateStr: string) => {
  try {
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return dateStr;
  }
};

const isToday = (date: Date) => {
  const today = new Date();
  return date.toDateString() === today.toDateString();
};

const isTomorrow = (date: Date) => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  return date.toDateString() === tomorrow.toDateString();
};

const isPast = (date: Date) => {
  return date < new Date();
};

const getEventDateLabel = (timeStr: string) => {
  try {
    const date = new Date(timeStr);
    if (isToday(date)) return 'Today';
    if (isTomorrow(date)) return 'Tomorrow';
    if (isPast(date)) return 'Past';
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
};

interface CalendarEvent {
  id: string;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  location?: string;
}

export default function CalendarView() {
  const { showSuccess, showError } = useToast();
  const queryClient = useQueryClient();
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [editingEvent, setEditingEvent] = useState<Partial<CalendarEvent>>({
    title: '',
    description: '',
    start_time: '',
    end_time: '',
    location: '',
  });

  // Fetch events
  const { data: eventsData, isLoading } = useQuery({
    queryKey: ['calendar-events'],
    queryFn: async () => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: { action: 'list' },
      }) as any;
      return (result?.result as any)?.events || [];
    },
  });

  const events: CalendarEvent[] = eventsData || [];

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (event: Partial<CalendarEvent>) => {
      return await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: {
          action: 'create',
          ...event,
        },
      }) as any;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] });
      setIsCreating(false);
      setEditingEvent({ title: '', description: '', start_time: '', end_time: '', location: '' });
      showSuccess('Event created');
    },
    onError: (error: any) => {
      showError(`Failed to create event: ${error.message}`);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async ({ eventId, event }: { eventId: string; event: Partial<CalendarEvent> }) => {
      return await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: {
          action: 'update',
          event_id: eventId,
          ...event,
        },
      }) as any;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] });
      setSelectedEvent(null);
      showSuccess('Event updated');
    },
    onError: (error: any) => {
      showError(`Failed to update event: ${error.message}`);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (eventId: string) => {
      return await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: {
          action: 'delete',
          event_id: eventId,
        },
      }) as any;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] });
      setSelectedEvent(null);
      showSuccess('Event deleted');
    },
    onError: (error: any) => {
      showError(`Failed to delete event: ${error.message}`);
    },
  });

  // Clear mutation
  const clearMutation = useMutation({
    mutationFn: async () => {
      return await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: { action: 'clear' },
      }) as any;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] });
      setSelectedEvent(null);
      showSuccess('All calendar events cleared');
    },
    onError: (error: any) => {
      showError(`Failed to clear calendar: ${error.message}`);
    },
  });

  const handleClearCalendar = () => {
    if (confirm('Are you sure you want to delete ALL calendar events? This cannot be undone.')) {
      clearMutation.mutate();
    }
  };

  // Export mutation
  const exportMutation = useMutation({
    mutationFn: async () => {
      return await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: { action: 'export' },
      }) as any;
    },
    onSuccess: () => {
      showSuccess('Calendar exported successfully');
      // Could trigger download here if needed
    },
    onError: (error: any) => {
      showError(`Failed to export calendar: ${error.message}`);
    },
  });

  const handleCreateNew = () => {
    setIsCreating(true);
    setSelectedEvent(null);
    const now = new Date();
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    // Format for datetime-local input (YYYY-MM-DDTHH:mm)
    const formatForInput = (date: Date) => {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      return `${year}-${month}-${day}T${hours}:${minutes}`;
    };
    
    setEditingEvent({
      title: '',
      description: '',
      start_time: formatForInput(now),
      end_time: formatForInput(tomorrow),
      location: '',
    });
  };

  const handleSelectEvent = (event: CalendarEvent) => {
    setSelectedEvent(event);
    setIsCreating(false);
    setEditingEvent({
      title: event.title,
      description: event.description || '',
      start_time: event.start_time.substring(0, 16), // Format for datetime-local input
      end_time: event.end_time.substring(0, 16),
      location: event.location || '',
    });
  };

  const handleSave = () => {
    if (!editingEvent.title || !editingEvent.start_time || !editingEvent.end_time) {
      showError('Title, start time, and end time are required');
      return;
    }

    if (isCreating) {
      createMutation.mutate(editingEvent);
    } else if (selectedEvent) {
      updateMutation.mutate({ eventId: selectedEvent.id, event: editingEvent });
    }
  };

  const handleDelete = (eventId: string, e?: React.MouseEvent) => {
    e?.preventDefault();
    e?.stopPropagation();
    
    if (pendingDeleteId === eventId) {
      // Second click - confirm delete
      if (!deleteMutation.isPending) {
        deleteMutation.mutate(eventId, {
          onSuccess: () => {
            setPendingDeleteId(null);
          },
          onError: () => {
            setPendingDeleteId(null);
          }
        });
      }
    } else {
      // First click - show confirmation state
      setPendingDeleteId(eventId);
      // Reset after 3 seconds if not confirmed
      setTimeout(() => setPendingDeleteId(null), 3000);
    }
  };

  const formatEventTime = (timeStr: string) => {
    return formatDate(timeStr);
  };

  // Sort events by start time
  const sortedEvents = [...events].sort((a, b) => {
    return new Date(a.start_time).getTime() - new Date(b.start_time).getTime();
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <CalendarIcon size={20} />
          <h4 className="font-semibold">Calendar</h4>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => exportMutation.mutate()} size="sm" variant="outline">
            <Download size={16} className="mr-1" />
            Export
          </Button>
          <Button 
            onClick={handleClearCalendar} 
            size="sm" 
            variant="outline"
            className="text-destructive hover:text-destructive"
            disabled={clearMutation.isPending}
          >
            <Trash2 size={16} className="mr-1" />
            Clear All
          </Button>
          <Button onClick={handleCreateNew} size="sm">
            <Plus size={16} className="mr-1" />
            New Event
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Events List */}
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle className="text-sm">Events</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[500px]">
              {isLoading ? (
                <div className="p-4 text-sm text-muted-foreground">Loading...</div>
              ) : sortedEvents.length === 0 ? (
                <div className="p-4 text-sm text-muted-foreground">No events yet</div>
              ) : (
                <div className="divide-y">
                  {sortedEvents.map((event) => (
                    <div
                      key={event.id}
                      className={`p-3 cursor-pointer hover:bg-muted transition-colors ${
                        selectedEvent?.id === event.id ? 'bg-muted border-l-2 border-primary' : ''
                      }`}
                      onClick={() => handleSelectEvent(event)}
                    >
                      <div className="font-medium text-sm">{event.title}</div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {getEventDateLabel(event.start_time)} • {formatEventTime(event.start_time)}
                      </div>
                      {event.location && (
                        <div className="text-xs text-muted-foreground mt-1">📍 {event.location}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Event Editor */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm">
              {isCreating ? 'Create New Event' : selectedEvent ? 'Edit Event' : 'Select an event to edit'}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {(!selectedEvent && !isCreating) ? (
              <div className="text-center text-muted-foreground py-8">
                Select an event from the list or create a new one
              </div>
            ) : (
              <>
                <div>
                  <Label className="block text-sm font-medium mb-1">Title *</Label>
                  <Input
                    type="text"
                    value={editingEvent.title || ''}
                    onChange={(e) => setEditingEvent({ ...editingEvent, title: e.target.value })}
                    className="w-full"
                    placeholder="Event title"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="block text-sm font-medium mb-1">Start Time *</Label>
                    <Input
                      type="datetime-local"
                      value={editingEvent.start_time || ''}
                      onChange={(e) => setEditingEvent({ ...editingEvent, start_time: e.target.value })}
                      className="w-full"
                    />
                  </div>
                  <div>
                    <Label className="block text-sm font-medium mb-1">End Time *</Label>
                    <Input
                      type="datetime-local"
                      value={editingEvent.end_time || ''}
                      onChange={(e) => setEditingEvent({ ...editingEvent, end_time: e.target.value })}
                      className="w-full"
                    />
                  </div>
                </div>

                <div>
                  <Label className="block text-sm font-medium mb-1">Location</Label>
                  <Input
                    type="text"
                    value={editingEvent.location || ''}
                    onChange={(e) => setEditingEvent({ ...editingEvent, location: e.target.value })}
                    className="w-full"
                    placeholder="Event location"
                  />
                </div>

                <div>
                  <Label className="block text-sm font-medium mb-1">Description</Label>
                  <Textarea
                    value={editingEvent.description || ''}
                    onChange={(e) => setEditingEvent({ ...editingEvent, description: e.target.value })}
                    className="w-full"
                    rows={4}
                    placeholder="Event description..."
                  />
                </div>

                <div className="flex gap-2">
                  <Button onClick={handleSave} className="flex-1" disabled={!editingEvent.title}>
                    {isCreating ? 'Create Event' : 'Save Changes'}
                  </Button>
                  {selectedEvent && (
                    <Button
                      type="button"
                      onClick={(e) => handleDelete(selectedEvent.id, e)}
                      variant={pendingDeleteId === selectedEvent.id ? "destructive" : "outline"}
                      disabled={deleteMutation.isPending}
                      className={cn(
                        pendingDeleteId === selectedEvent.id ? "bg-destructive text-destructive-foreground" : ""
                      )}
                    >
                      {deleteMutation.isPending ? (
                        "Deleting..."
                      ) : pendingDeleteId === selectedEvent.id ? (
                        "Confirm"
                      ) : (
                        <>
                          <Trash2 size={16} className="mr-1" />
                          Delete
                        </>
                      )}
                    </Button>
                  )}
                  {isCreating && (
                    <Button
                      onClick={() => {
                        setIsCreating(false);
                        setEditingEvent({ title: '', description: '', start_time: '', end_time: '', location: '' });
                      }}
                      variant="outline"
                    >
                      Cancel
                    </Button>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

