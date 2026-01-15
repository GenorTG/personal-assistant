'use client';

import { useState, useMemo, useCallback } from 'react';
import { Calendar as CalendarIcon, ListTodo, CalendarDays } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Calendar from './Calendar';
import Todo from './Todo';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { CalendarEvent } from '@/types/calendar';
import type { Todo as TodoType } from '@/types/todo';

interface OrganizerProps {
  onClose?: () => void;
}

export default function Organizer({ onClose }: OrganizerProps) {
  const [activeTab, setActiveTab] = useState<'calendar' | 'todos' | 'combined'>('combined');

  // Fetch both calendar events and todos for integration
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
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  const { data: todosData } = useQuery({
    queryKey: ['todos'],
    queryFn: async () => {
      interface ToolExecuteResponse {
        result?: {
          todos?: TodoType[];
        };
        error?: string;
      }
      const result = await api.post('/api/tools/execute', {
        tool_name: 'todo',
        parameters: { action: 'list', filter_status: 'all' },
      }) as ToolExecuteResponse;
      return result?.result?.todos || [];
    },
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  const events: CalendarEvent[] = useMemo(() => eventsData || [], [eventsData]);
  const todos: TodoType[] = useMemo(() => todosData || [], [todosData]);

  // Group todos by due date for calendar integration
  const todosByDate = useMemo(() => {
    const map = new Map<string, TodoType[]>();
    todos.forEach((todo) => {
      if (todo.due_date) {
        try {
          const date = new Date(todo.due_date);
          const dateKey = date.toDateString();
          if (!map.has(dateKey)) {
            map.set(dateKey, []);
          }
          map.get(dateKey)!.push(todo);
        } catch {
          // Skip invalid dates
        }
      }
    });
    return map;
  }, [todos]);

  // Get todos for a specific date
  const getTodosForDate = useCallback((date: Date): TodoType[] => {
    const dateKey = date.toDateString();
    return todosByDate.get(dateKey) || [];
  }, [todosByDate]);

  // Enhanced calendar with todos integration
  const CalendarWithTodos = () => {
    return (
      <div className="h-full w-full">
        <Calendar 
          onClose={onClose}
          todosByDate={todosByDate}
          getTodosForDate={getTodosForDate}
        />
      </div>
    );
  };

  return (
    <div className="h-full w-full flex flex-col">
      {/* Header with tabs */}
      <div className="border-b bg-background px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-5 w-5" />
          <h1 className="text-xl font-semibold">Organizer</h1>
        </div>
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)}>
          <TabsList>
            <TabsTrigger value="combined">
              <CalendarDays className="h-4 w-4 mr-2" />
              Combined
            </TabsTrigger>
            <TabsTrigger value="calendar">
              <CalendarIcon className="h-4 w-4 mr-2" />
              Calendar
            </TabsTrigger>
            <TabsTrigger value="todos">
              <ListTodo className="h-4 w-4 mr-2" />
              Todos
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'combined' && <CalendarWithTodos />}
        {activeTab === 'calendar' && (
          <div className="h-full">
            <Calendar onClose={onClose} />
          </div>
        )}
        {activeTab === 'todos' && (
          <div className="h-full">
            <Todo onClose={onClose} />
          </div>
        )}
      </div>
    </div>
  );
}
