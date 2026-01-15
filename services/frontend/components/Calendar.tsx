'use client';

import { useState, useMemo, useCallback } from 'react';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, Plus, Trash2, Download, X, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import type { CalendarEvent } from '@/types/calendar';

type ViewMode = 'day' | 'week' | 'month' | 'year';

// Date utilities
const formatDateShort = (date: Date) => {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const formatTime = (date: Date) => {
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
};

const getDaysInMonth = (date: Date) => {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
};

const getFirstDayOfMonth = (date: Date) => {
  return new Date(date.getFullYear(), date.getMonth(), 1).getDay();
};

const getWeekDates = (date: Date): Date[] => {
  const week: Date[] = [];
  const startOfWeek = new Date(date);
  const day = startOfWeek.getDay();
  const diff = startOfWeek.getDate() - day;
  startOfWeek.setDate(diff);
  
  for (let i = 0; i < 7; i++) {
    const d = new Date(startOfWeek);
    d.setDate(startOfWeek.getDate() + i);
    week.push(d);
  }
  return week;
};

const isSameDay = (date1: Date, date2: Date) => {
  return date1.toDateString() === date2.toDateString();
};

const isToday = (date: Date) => {
  return isSameDay(date, new Date());
};

interface CalendarProps {
  onClose?: () => void;
  todosByDate?: Map<string, any[]>;
  getTodosForDate?: (date: Date) => any[];
}

export default function Calendar({ onClose, todosByDate, getTodosForDate }: CalendarProps) {
  const { showSuccess, showError } = useToast();
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = useState<ViewMode>('month');
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [selectedDate, setSelectedDate] = useState<Date>(new Date());
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [eventsSidebarPosition, setEventsSidebarPosition] = useState<'left' | 'right'>('right');
  const [editingEvent, setEditingEvent] = useState<Partial<CalendarEvent>>({
    title: '',
    description: '',
    start_time: '',
    end_time: '',
    location: '',
    all_day: false,
  });

  // Fetch events with aggressive caching
  const { data: eventsData } = useQuery({
    queryKey: ['calendar-events'],
    queryFn: async () => {
      interface ToolExecuteResponse {
        result?: {
          events?: CalendarEvent[];
        };
        error?: string;
      }
      const result = await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: { action: 'list' },
      }) as ToolExecuteResponse;
      return result?.result?.events || [];
    },
    staleTime: 5 * 60 * 1000, // 5 minutes - calendar data doesn't change often
    gcTime: 30 * 60 * 1000, // 30 minutes - keep in cache longer
    refetchOnWindowFocus: false, // Don't refetch on window focus
  });

  // Memoize events array to prevent unnecessary recalculations
  const events: CalendarEvent[] = useMemo(() => eventsData || [], [eventsData]);

  // Memoize events by date for O(1) lookup instead of filtering every time
  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    events.forEach((event) => {
      try {
        const eventDate = new Date(event.start_time);
        const dateKey = eventDate.toDateString();
        if (!map.has(dateKey)) {
          map.set(dateKey, []);
        }
        map.get(dateKey)!.push(event);
      } catch {
        // Skip invalid dates
      }
    });
    return map;
  }, [events]);

  // Detect overlapping events
  const eventsWithOverlaps = useMemo(() => {
    const eventsWithConflicts: CalendarEvent[] = events.map(event => {
      const conflicts: CalendarEvent[] = [];
      const eventStart = new Date(event.start_time);
      const eventEnd = new Date(event.end_time);
      
      events.forEach(otherEvent => {
        if (otherEvent.id === event.id) return;
        
        const otherStart = new Date(otherEvent.start_time);
        const otherEnd = new Date(otherEvent.end_time);
        
        // Check for overlap: one starts before the other ends and ends after the other starts
        if (eventStart < otherEnd && eventEnd > otherStart) {
          conflicts.push(otherEvent);
        }
      });
      
      return {
        ...event,
        conflicts: conflicts.length > 0 ? conflicts : undefined,
        has_conflicts: conflicts.length > 0
      };
    });
    
    return eventsWithConflicts;
  }, [events]);

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (event: Partial<CalendarEvent>) => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: {
          action: 'create',
          ...event,
        },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] });
      showSuccess('Event created successfully');
      setIsCreating(false);
      setEditingEvent({ title: '', description: '', start_time: '', end_time: '', location: '', all_day: false });
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to create event');
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async ({ id, ...event }: Partial<CalendarEvent> & { id: string }) => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: {
          action: 'update',
          event_id: id,
          ...event,
        },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] });
      showSuccess('Event updated successfully');
      setSelectedEvent(null);
      setEditingEvent({ title: '', description: '', start_time: '', end_time: '', location: '', all_day: false });
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to update event');
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (eventId: string) => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: {
          action: 'delete',
          event_id: eventId,
        },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] });
      showSuccess('Event deleted successfully');
      setPendingDeleteId(null);
      setSelectedEvent(null);
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to delete event');
      setPendingDeleteId(null);
    },
  });

  // Export mutation
  const exportMutation = useMutation({
    mutationFn: async () => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: { action: 'export' },
      });
      return result;
    },
    onSuccess: () => {
      showSuccess('Calendar exported successfully');
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to export calendar');
    },
  });

  // Clear mutation
  const clearMutation = useMutation({
    mutationFn: async () => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'calendar',
        parameters: { action: 'clear' },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-events'] });
      showSuccess('All calendar events cleared');
      setSelectedEvent(null);
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to clear calendar');
    },
  });

  const handleClearCalendar = () => {
    if (confirm('Are you sure you want to delete ALL calendar events? This cannot be undone.')) {
      clearMutation.mutate();
    }
  };

  const handleSelectEvent = useCallback((event: CalendarEvent) => {
    setSelectedEvent(event);
    setEditingEvent({
      title: event.title || '',
      description: event.description || '',
      start_time: event.start_time || '',
      end_time: event.end_time || '',
      location: event.location || '',
    });
    setIsCreating(false);
  }, []);

  const handleCreateNew = useCallback(() => {
    setIsCreating(true);
    setSelectedEvent(null);
    setEditingEvent({
      title: '',
      description: '',
      start_time: '',
      end_time: '',
      location: '',
      all_day: false,
    });
  }, []);

  const handleSave = () => {
    if (!editingEvent.title || !editingEvent.start_time || !editingEvent.end_time) {
      showError('Please fill in all required fields');
      return;
    }

    if (isCreating) {
      createMutation.mutate(editingEvent);
    } else if (selectedEvent?.id) {
      updateMutation.mutate({ id: selectedEvent.id, ...editingEvent });
    }
  };

  const handleDeleteClick = (eventId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (pendingDeleteId === eventId) {
      deleteMutation.mutate(eventId);
    } else {
      setPendingDeleteId(eventId);
      setTimeout(() => setPendingDeleteId(null), 3000);
    }
  };

  // Navigation
  const goToToday = () => {
    const today = new Date();
    setCurrentDate(today);
    setSelectedDate(today);
  };

  const goToPrevious = () => {
    const newDate = new Date(currentDate);
    if (viewMode === 'year') {
      newDate.setFullYear(newDate.getFullYear() - 1);
    } else if (viewMode === 'month') {
      newDate.setMonth(newDate.getMonth() - 1);
    } else if (viewMode === 'week') {
      newDate.setDate(newDate.getDate() - 7);
    } else {
      newDate.setDate(newDate.getDate() - 1);
    }
    setCurrentDate(newDate);
  };

  const goToNext = () => {
    const newDate = new Date(currentDate);
    if (viewMode === 'year') {
      newDate.setFullYear(newDate.getFullYear() + 1);
    } else if (viewMode === 'month') {
      newDate.setMonth(newDate.getMonth() + 1);
    } else if (viewMode === 'week') {
      newDate.setDate(newDate.getDate() + 7);
    } else {
      newDate.setDate(newDate.getDate() + 1);
    }
    setCurrentDate(newDate);
  };

  // Get events for a specific date - optimized with memoized map
  const getEventsForDate = useCallback((date: Date): CalendarEvent[] => {
    const dateKey = date.toDateString();
    return eventsByDate.get(dateKey) || [];
  }, [eventsByDate]);

  // Get todos for a specific date
  const getTodosForDateLocal = useCallback((date: Date): any[] => {
    if (getTodosForDate) {
      return getTodosForDate(date);
    }
    if (todosByDate) {
      const dateKey = date.toDateString();
      return todosByDate.get(dateKey) || [];
    }
    return [];
  }, [todosByDate, getTodosForDate]);

  // Year view
  const renderYearView = () => {
    const year = currentDate.getFullYear();
    const months = Array.from({ length: 12 }, (_, i) => new Date(year, i, 1));

    return (
      <div className="grid grid-cols-3 gap-4 p-2">
        {months.map((monthDate, idx) => {
          const monthEvents = events.filter((event) => {
            try {
              const eventDate = new Date(event.start_time);
              return eventDate.getFullYear() === year && eventDate.getMonth() === idx;
            } catch {
              return false;
            }
          });

          return (
            <div
              key={idx}
              className={cn(
                "border rounded p-3 cursor-pointer hover:bg-muted transition-colors",
                monthDate.getMonth() === new Date().getMonth() && monthDate.getFullYear() === new Date().getFullYear() && "ring-2 ring-primary"
              )}
              onClick={() => {
                setCurrentDate(monthDate);
                setViewMode('month');
              }}
            >
              <div className="text-sm font-semibold mb-2">
                {monthDate.toLocaleDateString('en-US', { month: 'long' })}
              </div>
              <div className="text-xs text-muted-foreground">
                {monthEvents.length} event{monthEvents.length !== 1 ? 's' : ''}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // Month view
  const renderMonthView = () => {
    const daysInMonth = getDaysInMonth(currentDate);
    const firstDay = getFirstDayOfMonth(currentDate);
    const days: (Date | null)[] = [];

    for (let i = 0; i < firstDay; i++) {
      days.push(null);
    }

    for (let day = 1; day <= daysInMonth; day++) {
      days.push(new Date(currentDate.getFullYear(), currentDate.getMonth(), day));
    }

    return (
      <div className="grid grid-cols-7 gap-1 p-2">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
          <div key={day} className="text-center text-xs font-semibold text-muted-foreground p-1">
            {day}
          </div>
        ))}
        {days.map((date, index) => {
          if (!date) {
            return <div key={index} className="aspect-square" />;
          }
          const dayEvents = getEventsForDate(date);
          const isCurrentDay = isToday(date);
          const isSelected = selectedDate && isSameDay(selectedDate, date);
          const isCurrentMonth = date.getMonth() === currentDate.getMonth();

          return (
            <div
              key={index}
              className={cn(
                "aspect-square border rounded p-1 relative cursor-pointer transition-colors text-xs",
                !isCurrentMonth && "opacity-30",
                isCurrentDay && "ring-2 ring-primary",
                isSelected && "bg-primary/20 border-primary",
                !isSelected && !isCurrentDay && "hover:bg-muted"
              )}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                // Optimistic update - update state immediately for instant feedback
                setSelectedDate(date);
                // Only update currentDate if needed (for month navigation)
                if (date.getMonth() !== currentDate.getMonth() || date.getFullYear() !== currentDate.getFullYear()) {
                  setCurrentDate(date);
                }
              }}
            >
              <div className={cn("text-xs font-medium", isCurrentDay && "text-primary font-bold")}>
                {date.getDate()}
              </div>
              {dayEvents.length > 0 && (
                <div className="mt-0.5">
                  <div className="h-1 w-full bg-primary/30 rounded" />
                </div>
              )}
              {getTodosForDateLocal && getTodosForDateLocal(date).length > 0 && (
                <div className="mt-0.5 flex gap-0.5">
                  {getTodosForDateLocal(date).slice(0, 3).map((todo: any) => (
                    <div
                      key={todo.id}
                      className={cn(
                        "h-1 flex-1 rounded",
                        todo.status === 'completed' ? 'bg-green-400' :
                        todo.priority === 'urgent' ? 'bg-red-500' :
                        todo.priority === 'high' ? 'bg-orange-400' :
                        todo.priority === 'medium' ? 'bg-blue-400' : 'bg-gray-400'
                      )}
                      title={`${todo.title}${todo.status === 'completed' ? ' (completed)' : ''}`}
                    />
                  ))}
                  {getTodosForDateLocal(date).length > 3 && (
                    <div className="h-1 w-1 bg-gray-400 rounded" title={`+${getTodosForDateLocal(date).length - 3} more todos`} />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  // Week view
  const renderWeekView = () => {
    const weekDates = getWeekDates(currentDate);

    return (
      <div className="grid grid-cols-7 gap-2 p-2">
        {weekDates.map((date, index) => {
          const dayEvents = getEventsForDate(date);
          const dayTodos = getTodosForDateLocal ? getTodosForDateLocal(date) : [];
          const isCurrentDay = isToday(date);
          const isSelected = selectedDate && isSameDay(selectedDate, date);
          const dayName = date.toLocaleDateString('en-US', { weekday: 'short' });

          return (
            <div
              key={index}
              className={cn(
                "border rounded p-2 cursor-pointer transition-colors",
                isCurrentDay && "ring-2 ring-primary",
                isSelected && "bg-primary/20 border-primary",
                !isSelected && !isCurrentDay && "hover:bg-muted"
              )}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                // Optimistic update - update state immediately for instant feedback
                setSelectedDate(date);
                // Only update currentDate if needed (for month navigation)
                if (date.getMonth() !== currentDate.getMonth() || date.getFullYear() !== currentDate.getFullYear()) {
                  setCurrentDate(date);
                }
              }}
            >
              <div className={cn("text-xs font-semibold mb-1", isCurrentDay && "text-primary")}>
                <div>{dayName}</div>
                <div className="text-sm">{date.getDate()}</div>
              </div>
              <div className="space-y-1">
                {dayEvents.slice(0, 3).map((event) => {
                  const eventWithOverlaps = eventsWithOverlaps.find(e => e.id === event.id);
                  const hasConflicts = eventWithOverlaps?.has_conflicts || false;
                  
                  return (
                    <div
                      key={event.id}
                      className={cn(
                        "text-xs p-1 rounded truncate cursor-pointer",
                        hasConflicts 
                          ? "bg-destructive/20 text-destructive border border-destructive/50 hover:bg-destructive/30" 
                          : "bg-primary/20 text-primary hover:bg-primary/30"
                      )}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelectEvent(event);
                      }}
                      title={hasConflicts ? `⚠️ Overlaps with ${eventWithOverlaps?.conflicts?.length || 0} other event(s)` : undefined}
                    >
                      {hasConflicts && "⚠️ "}
                      {formatTime(new Date(event.start_time))} {event.title}
                    </div>
                  );
                })}
                {dayEvents.length > 3 && (
                  <div className="text-xs text-muted-foreground">+{dayEvents.length - 3} more events</div>
                )}
                {dayTodos.length > 0 && (
                  <div className="mt-1 space-y-0.5">
                    {dayTodos.slice(0, 2).map((todo: any) => (
                      <div
                        key={todo.id}
                        className={cn(
                          "text-xs px-1 py-0.5 rounded truncate",
                          todo.status === 'completed' 
                            ? 'bg-green-100 text-green-700 line-through' 
                            : todo.priority === 'urgent'
                            ? 'bg-red-100 text-red-700'
                            : todo.priority === 'high'
                            ? 'bg-orange-100 text-orange-700'
                            : 'bg-blue-100 text-blue-700'
                        )}
                        title={todo.title}
                      >
                        {todo.status === 'completed' ? '✓ ' : '○ '}
                        {todo.title}
                      </div>
                    ))}
                    {dayTodos.length > 2 && (
                      <div className="text-xs text-muted-foreground">+{dayTodos.length - 2} more todos</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // Day view
  const renderDayView = () => {
    const dayEvents = getEventsForDate(currentDate);
    const dayTodos = getTodosForDateLocal ? getTodosForDateLocal(currentDate) : [];
    const isCurrentDay = isToday(currentDate);
    const hours = Array.from({ length: 24 }, (_, i) => i);

    return (
      <div className="p-2">
        <div className={cn("text-sm font-semibold mb-3", isCurrentDay && "text-primary")}>
          {currentDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
        </div>
        <div className="space-y-1">
          {hours.map((hour) => {
            const hourEvents = dayEvents.filter((event) => {
              try {
                const eventDate = new Date(event.start_time);
                return eventDate.getHours() === hour;
              } catch {
                return false;
              }
            });

            return (
              <div key={hour} className="border-b border-border/50 p-2 min-h-[50px]">
                <div className="text-xs text-muted-foreground mb-1">
                  {hour === 0 ? '12 AM' : hour < 12 ? `${hour} AM` : hour === 12 ? '12 PM' : `${hour - 12} PM`}
                </div>
                <div className="space-y-1">
                  {hourEvents.map((event) => {
                    const eventWithOverlaps = eventsWithOverlaps.find(e => e.id === event.id);
                    const hasConflicts = eventWithOverlaps?.has_conflicts || false;
                    
                    return (
                      <div
                        key={event.id}
                        className={cn(
                          "p-2 rounded text-xs cursor-pointer",
                          hasConflicts 
                            ? "bg-destructive/20 text-destructive border border-destructive/50 hover:bg-destructive/30" 
                            : "bg-primary/20 text-primary hover:bg-primary/30"
                        )}
                        onClick={() => handleSelectEvent(event)}
                        title={hasConflicts ? `⚠️ Overlaps with ${eventWithOverlaps?.conflicts?.length || 0} other event(s)` : undefined}
                      >
                        <div className="font-medium flex items-center gap-1">
                          {hasConflicts && <span className="text-destructive">⚠️</span>}
                          {event.title}
                        </div>
                        {event.location && (
                          <div className="text-xs text-muted-foreground">📍 {event.location}</div>
                        )}
                        {hasConflicts && eventWithOverlaps?.conflicts && eventWithOverlaps.conflicts.length > 0 && (
                          <div className="text-xs text-destructive/80 mt-1">
                            Conflicts: {eventWithOverlaps.conflicts.map(c => c.title).join(', ')}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const selectedDateEvents = useMemo(() => getEventsForDate(selectedDate), [selectedDate, getEventsForDate]);

  const renderEventsSidebar = (side: 'left' | 'right') => (
    <div className={cn("w-80 flex flex-col bg-muted/20", side === 'left' ? "border-r border-border" : "border-l border-border")}>
      <div className="flex-shrink-0 border-b border-border p-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          {selectedDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
        </h3>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => setEventsSidebarPosition(eventsSidebarPosition === 'left' ? 'right' : 'left')}
            title="Toggle sidebar position"
          >
            <Settings2 size={12} />
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {getTodosForDateLocal && getTodosForDateLocal(selectedDate).length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm font-semibold mb-2">Todos for this day</h3>
            <div className="space-y-1">
              {getTodosForDateLocal(selectedDate).map((todo: any) => (
                <div
                  key={todo.id}
                  className={cn(
                    "p-2 rounded text-sm border cursor-pointer hover:bg-accent",
                    todo.status === 'completed' 
                      ? 'bg-green-50 border-green-200 line-through' 
                      : todo.priority === 'urgent'
                      ? 'bg-red-50 border-red-200'
                      : todo.priority === 'high'
                      ? 'bg-orange-50 border-orange-200'
                      : 'bg-blue-50 border-blue-200'
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      "text-xs",
                      todo.status === 'completed' ? 'text-green-600' : 'text-gray-500'
                    )}>
                      {todo.status === 'completed' ? '✓' : '○'}
                    </span>
                    <span className="flex-1 font-medium">{todo.title}</span>
                    {todo.priority && (
                      <span className={cn(
                        "text-xs px-1.5 py-0.5 rounded",
                        todo.priority === 'urgent' ? 'bg-red-200 text-red-800' :
                        todo.priority === 'high' ? 'bg-orange-200 text-orange-800' :
                        todo.priority === 'medium' ? 'bg-blue-200 text-blue-800' : 'bg-gray-200 text-gray-800'
                      )}>
                        {todo.priority}
                      </span>
                    )}
                  </div>
                  {todo.description && (
                    <p className="text-xs text-muted-foreground mt-1 ml-5">{todo.description}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        {selectedDateEvents.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground text-sm">
            <p className="mb-3">No events for this day</p>
            <Button
              size="sm"
              onClick={() => {
                handleCreateNew();
                const formatForInput = (d: Date) => {
                  const year = d.getFullYear();
                  const month = String(d.getMonth() + 1).padStart(2, '0');
                  const day = String(d.getDate()).padStart(2, '0');
                  return `${year}-${month}-${day}T12:00`;
                };
                setEditingEvent({
                  ...editingEvent,
                  start_time: formatForInput(selectedDate),
                  end_time: formatForInput(new Date(selectedDate.getTime() + 60 * 60 * 1000)),
                });
              }}
            >
              <Plus size={14} className="mr-1" />
              Add Event
            </Button>
          </div>
        ) : (
          <>
            <h3 className="text-sm font-semibold mb-2">Events for this day</h3>
            {selectedDateEvents.map((event) => {
              const eventWithOverlaps = eventsWithOverlaps.find(e => e.id === event.id);
              const hasConflicts = eventWithOverlaps?.has_conflicts || false;
              
              return (
                <div
                  key={event.id}
                  className={cn(
                    "border rounded p-3 cursor-pointer transition-colors",
                    hasConflicts && "border-destructive/50 bg-destructive/5",
                    selectedEvent?.id === event.id ? "bg-primary/10 border-primary" : "hover:bg-muted"
                  )}
                  onClick={() => handleSelectEvent(event)}
                >
                  <div className="font-medium text-sm flex items-center gap-1">
                    {hasConflicts && <span className="text-destructive" title={`Overlaps with ${eventWithOverlaps?.conflicts?.length || 0} event(s)`}>⚠️</span>}
                    {event.title}
                    {event.all_day && <span className="text-xs text-muted-foreground">(All Day)</span>}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {formatTime(new Date(event.start_time))} - {formatTime(new Date(event.end_time))}
                  </div>
                  {hasConflicts && eventWithOverlaps?.conflicts && eventWithOverlaps.conflicts.length > 0 && (
                    <div className="text-xs text-destructive/80 mt-1 border-t border-destructive/20 pt-1">
                      ⚠️ Conflicts with: {eventWithOverlaps.conflicts.map(c => c.title).join(', ')}
                    </div>
                  )}
                  {event.location && (
                    <div className="text-xs text-muted-foreground mt-1">📍 {event.location}</div>
                  )}
                  {event.description && (
                    <div className="text-xs text-muted-foreground mt-1 line-clamp-2">{event.description}</div>
                  )}
                  <div className="flex items-center gap-1 mt-2">
                    <div
                      onClick={(e) => handleDeleteClick(event.id, e)}
                      className={cn(
                        "text-xs px-2 py-1 rounded transition-colors cursor-pointer",
                        pendingDeleteId === event.id
                          ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          : "text-destructive hover:bg-muted",
                        deleteMutation.isPending && "opacity-50 cursor-not-allowed"
                      )}
                      title={pendingDeleteId === event.id ? "Click again to confirm" : "Delete"}
                    >
                      {pendingDeleteId === event.id ? "Confirm" : <Trash2 size={12} />}
                    </div>
                  </div>
                </div>
              );
            })}
            <Button
              size="sm"
              variant="outline"
              className="w-full mt-2"
              onClick={() => {
                handleCreateNew();
                const formatForInput = (d: Date) => {
                  const year = d.getFullYear();
                  const month = String(d.getMonth() + 1).padStart(2, '0');
                  const day = String(d.getDate()).padStart(2, '0');
                  return `${year}-${month}-${day}T12:00`;
                };
                setEditingEvent({
                  ...editingEvent,
                  start_time: formatForInput(selectedDate),
                  end_time: formatForInput(new Date(selectedDate.getTime() + 60 * 60 * 1000)),
                });
              }}
            >
              <Plus size={14} className="mr-1" />
              Add Event
            </Button>
          </>
        )}
      </div>
    </div>
  );

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-border p-3">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <CalendarIcon size={20} />
            <h2 className="text-lg font-semibold">Calendar</h2>
          </div>
          {onClose && (
            <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8">
              <X size={16} />
            </Button>
          )}
        </div>

        {/* View Controls */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={goToPrevious} className="h-7 px-2">
              <ChevronLeft size={14} />
            </Button>
            <Button variant="outline" size="sm" onClick={goToToday} className="h-7 px-2">
              Today
            </Button>
            <Button variant="outline" size="sm" onClick={goToNext} className="h-7 px-2">
              <ChevronRight size={14} />
            </Button>
            <div className="ml-3 text-sm font-semibold">
              {viewMode === 'year' && currentDate.getFullYear()}
              {viewMode === 'month' && currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
              {viewMode === 'week' && (() => {
                const weekDates = getWeekDates(currentDate);
                return `${formatDateShort(weekDates[0])} - ${formatDateShort(weekDates[6])}`;
              })()}
              {viewMode === 'day' && currentDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex border border-border rounded">
              <Button
                variant={viewMode === 'day' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('day')}
                className="h-7 px-2 rounded-r-none text-xs"
              >
                Day
              </Button>
              <Button
                variant={viewMode === 'week' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('week')}
                className="h-7 px-2 rounded-none border-x text-xs"
              >
                Week
              </Button>
              <Button
                variant={viewMode === 'month' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('month')}
                className="h-7 px-2 rounded-none border-x text-xs"
              >
                Month
              </Button>
              <Button
                variant={viewMode === 'year' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('year')}
                className="h-7 px-2 rounded-l-none text-xs"
              >
                Year
              </Button>
            </div>
            <Button variant="outline" size="sm" onClick={() => exportMutation.mutate()} className="h-7 px-2">
              <Download size={14} className="mr-1" />
              Export
            </Button>
            <Button 
              variant="outline" 
              size="sm" 
              onClick={handleClearCalendar}
              className="h-7 px-2 text-destructive hover:text-destructive"
              disabled={clearMutation.isPending}
            >
              <Trash2 size={14} className="mr-1" />
              Clear All
            </Button>
            <Button size="sm" onClick={handleCreateNew} className="h-7 px-2">
              <Plus size={14} className="mr-1" />
              New
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden flex">
        {eventsSidebarPosition === 'left' && renderEventsSidebar('left')}
        
        <div className="flex-1 overflow-y-auto">
          {viewMode === 'year' && renderYearView()}
          {viewMode === 'month' && renderMonthView()}
          {viewMode === 'week' && renderWeekView()}
          {viewMode === 'day' && renderDayView()}
        </div>

        {eventsSidebarPosition === 'right' && renderEventsSidebar('right')}
      </div>

      {/* Event Editor */}
      {(selectedEvent || isCreating) && (
        <div className="flex-shrink-0 border-t border-border p-4 bg-muted/20">
          <div className="max-w-2xl mx-auto space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-sm">
                {isCreating ? 'Create New Event' : 'Edit Event'}
              </h3>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => {
                  setSelectedEvent(null);
                  setIsCreating(false);
                }}
              >
                <X size={14} />
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Title *</Label>
                <Input
                  value={editingEvent.title || ''}
                  onChange={(e) => setEditingEvent({ ...editingEvent, title: e.target.value })}
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <Label className="text-xs">Location</Label>
                <Input
                  value={editingEvent.location || ''}
                  onChange={(e) => setEditingEvent({ ...editingEvent, location: e.target.value })}
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <Label className="text-xs">Start Time *</Label>
                <Input
                  type="datetime-local"
                  value={editingEvent.start_time || ''}
                  onChange={(e) => setEditingEvent({ ...editingEvent, start_time: e.target.value })}
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <Label className="text-xs">End Time *</Label>
                <Input
                  type="datetime-local"
                  value={editingEvent.end_time || ''}
                  onChange={(e) => setEditingEvent({ ...editingEvent, end_time: e.target.value })}
                  className="h-8 text-sm"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs">Description</Label>
              <Textarea
                value={editingEvent.description || ''}
                onChange={(e) => setEditingEvent({ ...editingEvent, description: e.target.value })}
                className="text-sm min-h-[60px]"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="all-day"
                checked={editingEvent.all_day || false}
                onCheckedChange={(checked) => setEditingEvent({ ...editingEvent, all_day: !!checked })}
              />
              <Label htmlFor="all-day" className="text-xs cursor-pointer">
                All Day Event
              </Label>
            </div>
            <div className="flex items-center justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSelectedEvent(null);
                  setIsCreating(false);
                }}
                className="h-8"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={createMutation.isPending || updateMutation.isPending}
                className="h-8"
              >
                {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
