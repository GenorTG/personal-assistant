'use client';

import { useState, useMemo, useCallback } from 'react';
import { CheckCircle2, Circle, Plus, Trash2, Edit2, X, Filter, Flag, Calendar as CalendarIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import type { Todo, TodoFilter } from '@/types/todo';

interface TodoProps {
  onClose?: () => void;
}

const priorityColors = {
  low: 'text-gray-500',
  medium: 'text-blue-500',
  high: 'text-orange-500',
  urgent: 'text-red-500',
};

const priorityBgColors = {
  low: 'bg-gray-100',
  medium: 'bg-blue-100',
  high: 'bg-orange-100',
  urgent: 'bg-red-100',
};

export default function Todo({ onClose }: TodoProps) {
  const { showSuccess, showError } = useToast();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<TodoFilter>({ status: 'all', priority: 'all' });
  const [selectedTodo, setSelectedTodo] = useState<Todo | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [editingTodo, setEditingTodo] = useState<Partial<Todo>>({
    title: '',
    description: '',
    priority: 'medium',
    status: 'pending',
    due_date: '',
    category: '',
  });
  const [showFilters, setShowFilters] = useState(false);

  // Fetch todos
  const { data: todosData } = useQuery({
    queryKey: ['todos', filter],
    queryFn: async () => {
      interface ToolExecuteResponse {
        result?: {
          todos?: Todo[];
        };
        error?: string;
      }
      const result = await api.post('/api/tools/execute', {
        tool_name: 'todo',
        parameters: {
          action: 'list',
          filter_status: filter.status || 'all',
          filter_priority: filter.priority || 'all',
          filter_category: filter.category,
        },
      }) as ToolExecuteResponse;
      return result?.result?.todos || [];
    },
    staleTime: 30 * 1000, // 30 seconds
    gcTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });

  const todos: Todo[] = useMemo(() => todosData || [], [todosData]);

  // Separate pending and completed todos
  const pendingTodos = useMemo(() => todos.filter(t => t.status === 'pending'), [todos]);
  const completedTodos = useMemo(() => todos.filter(t => t.status === 'completed'), [todos]);

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (todo: Partial<Todo>) => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'todo',
        parameters: {
          action: 'create',
          ...todo,
        },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] });
      showSuccess('Todo created successfully');
      setIsCreating(false);
      setEditingTodo({ title: '', description: '', priority: 'medium', status: 'pending', due_date: '', category: '' });
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to create todo');
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async ({ id, ...todo }: Partial<Todo> & { id: string }) => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'todo',
        parameters: {
          action: 'update',
          todo_id: id,
          ...todo,
        },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] });
      showSuccess('Todo updated successfully');
      setSelectedTodo(null);
      setEditingTodo({ title: '', description: '', priority: 'medium', status: 'pending', due_date: '', category: '' });
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to update todo');
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (todoId: string) => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'todo',
        parameters: {
          action: 'delete',
          todo_id: todoId,
        },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] });
      showSuccess('Todo deleted successfully');
      setSelectedTodo(null);
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to delete todo');
    },
  });

  // Complete mutation
  const completeMutation = useMutation({
    mutationFn: async (todoId: string) => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'todo',
        parameters: {
          action: 'complete',
          todo_id: todoId,
        },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] });
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to complete todo');
    },
  });

  // Uncomplete mutation
  const uncompleteMutation = useMutation({
    mutationFn: async (todoId: string) => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'todo',
        parameters: {
          action: 'uncomplete',
          todo_id: todoId,
        },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] });
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to uncomplete todo');
    },
  });

  // Clear completed mutation
  const clearCompletedMutation = useMutation({
    mutationFn: async () => {
      const result = await api.post('/api/tools/execute', {
        tool_name: 'todo',
        parameters: { action: 'clear_completed' },
      });
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] });
      showSuccess('Completed todos cleared');
    },
    onError: (error: any) => {
      showError(error?.message || 'Failed to clear completed todos');
    },
  });

  const handleSelectTodo = useCallback((todo: Todo) => {
    setSelectedTodo(todo);
    setEditingTodo({
      title: todo.title || '',
      description: todo.description || '',
      priority: todo.priority || 'medium',
      status: todo.status || 'pending',
      due_date: todo.due_date ? new Date(todo.due_date).toISOString().split('T')[0] : '',
      category: todo.category || '',
    });
    setIsCreating(false);
  }, []);

  const handleCreateNew = useCallback(() => {
    setIsCreating(true);
    setSelectedTodo(null);
    setEditingTodo({
      title: '',
      description: '',
      priority: 'medium',
      status: 'pending',
      due_date: '',
      category: '',
    });
  }, []);

  const handleSave = () => {
    if (!editingTodo.title) {
      showError('Please enter a title');
      return;
    }

    if (isCreating) {
      createMutation.mutate(editingTodo);
    } else if (selectedTodo?.id) {
      updateMutation.mutate({ id: selectedTodo.id, ...editingTodo });
    }
  };

  const handleDelete = (todoId: string) => {
    if (confirm('Are you sure you want to delete this todo?')) {
      deleteMutation.mutate(todoId);
    }
  };

  const handleToggleComplete = (todo: Todo) => {
    if (todo.status === 'completed') {
      uncompleteMutation.mutate(todo.id);
    } else {
      completeMutation.mutate(todo.id);
    }
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return null;
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return null;
    }
  };

  const isOverdue = (todo: Todo) => {
    if (!todo.due_date || todo.status === 'completed') return false;
    try {
      return new Date(todo.due_date) < new Date();
    } catch {
      return false;
    }
  };

  return (
    <div className="flex h-full w-full">
      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-bold">Todos</h1>
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <span>{pendingTodos.length} pending</span>
              <span>•</span>
              <span>{completedTodos.length} completed</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowFilters(!showFilters)}
            >
              <Filter className="h-4 w-4 mr-2" />
              Filters
            </Button>
            {completedTodos.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (confirm('Clear all completed todos?')) {
                    clearCompletedMutation.mutate();
                  }
                }}
              >
                Clear Completed
              </Button>
            )}
            <Button onClick={handleCreateNew}>
              <Plus className="h-4 w-4 mr-2" />
              New Todo
            </Button>
            {onClose && (
              <Button variant="ghost" size="sm" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        {/* Filters */}
        {showFilters && (
          <div className="p-4 border-b bg-gray-50">
            <div className="flex items-center gap-4">
              <div>
                <Label>Status</Label>
                <select
                  value={filter.status || 'all'}
                  onChange={(e) => setFilter({ ...filter, status: e.target.value as any })}
                  className="mt-1 block rounded border p-1"
                >
                  <option value="all">All</option>
                  <option value="pending">Pending</option>
                  <option value="completed">Completed</option>
                </select>
              </div>
              <div>
                <Label>Priority</Label>
                <select
                  value={filter.priority || 'all'}
                  onChange={(e) => setFilter({ ...filter, priority: e.target.value as any })}
                  className="mt-1 block rounded border p-1"
                >
                  <option value="all">All</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>
              <div>
                <Label>Category</Label>
                <Input
                  placeholder="Filter by category"
                  value={filter.category || ''}
                  onChange={(e) => setFilter({ ...filter, category: e.target.value || undefined })}
                  className="mt-1"
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setFilter({ status: 'all', priority: 'all' })}
              >
                Clear Filters
              </Button>
            </div>
          </div>
        )}

        {/* Todo List */}
        <div className="flex-1 overflow-y-auto p-4">
          {todos.length === 0 ? (
            <div className="text-center text-gray-500 mt-8">
              <p>No todos found. Create your first todo!</p>
            </div>
          ) : (
            <div className="space-y-2">
              {pendingTodos.map((todo) => (
                <div
                  key={todo.id}
                  className={cn(
                    "flex items-start gap-3 p-3 rounded border cursor-pointer hover:bg-gray-50 transition-colors",
                    isOverdue(todo) && "border-red-300 bg-red-50"
                  )}
                  onClick={() => handleSelectTodo(todo)}
                >
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleToggleComplete(todo);
                    }}
                    className="mt-0.5"
                  >
                    <Circle className={cn("h-5 w-5", priorityColors[todo.priority])} />
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className={cn("font-medium", todo.status === 'completed' && "line-through text-gray-500")}>
                        {todo.title}
                      </h3>
                      <span className={cn("text-xs px-2 py-0.5 rounded", priorityBgColors[todo.priority], priorityColors[todo.priority])}>
                        {todo.priority}
                      </span>
                      {todo.category && (
                        <span className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-700">
                          {todo.category}
                        </span>
                      )}
                    </div>
                    {todo.description && (
                      <p className="text-sm text-gray-600 mt-1 line-clamp-2">{todo.description}</p>
                    )}
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      {todo.due_date && (
                        <div className={cn("flex items-center gap-1", isOverdue(todo) && "text-red-600 font-medium")}>
                          <CalendarIcon className="h-3 w-3" />
                          {formatDate(todo.due_date)}
                          {isOverdue(todo) && ' (Overdue)'}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelectTodo(todo);
                      }}
                    >
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(todo.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}

              {completedTodos.length > 0 && (
                <>
                  <div className="mt-6 mb-2 text-sm font-medium text-gray-500">Completed</div>
                  {completedTodos.map((todo) => (
                    <div
                      key={todo.id}
                      className="flex items-start gap-3 p-3 rounded border bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
                      onClick={() => handleSelectTodo(todo)}
                    >
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleComplete(todo);
                        }}
                        className="mt-0.5"
                      >
                        <CheckCircle2 className="h-5 w-5 text-green-500" />
                      </button>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium line-through text-gray-500">
                            {todo.title}
                          </h3>
                          <span className={cn("text-xs px-2 py-0.5 rounded", priorityBgColors[todo.priority], priorityColors[todo.priority])}>
                            {todo.priority}
                          </span>
                          {todo.category && (
                            <span className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-700">
                              {todo.category}
                            </span>
                          )}
                        </div>
                        {todo.description && (
                          <p className="text-sm text-gray-600 mt-1 line-clamp-2">{todo.description}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(todo.id);
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Sidebar - Edit/Create */}
      {(isCreating || selectedTodo) && (
        <div className="w-96 border-l bg-white flex flex-col">
          <div className="p-4 border-b flex items-center justify-between">
            <h2 className="text-lg font-semibold">{isCreating ? 'Create Todo' : 'Edit Todo'}</h2>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setIsCreating(false);
                setSelectedTodo(null);
                setEditingTodo({ title: '', description: '', priority: 'medium', status: 'pending', due_date: '', category: '' });
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div>
              <Label>Title *</Label>
              <Input
                value={editingTodo.title || ''}
                onChange={(e) => setEditingTodo({ ...editingTodo, title: e.target.value })}
                placeholder="Enter todo title"
                className="mt-1"
              />
            </div>

            <div>
              <Label>Description</Label>
              <Textarea
                value={editingTodo.description || ''}
                onChange={(e) => setEditingTodo({ ...editingTodo, description: e.target.value })}
                placeholder="Enter description (optional)"
                className="mt-1"
                rows={4}
              />
            </div>

            <div>
              <Label>Priority</Label>
              <select
                value={editingTodo.priority || 'medium'}
                onChange={(e) => setEditingTodo({ ...editingTodo, priority: e.target.value as any })}
                className="mt-1 block w-full rounded border p-2"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>

            <div>
              <Label>Due Date</Label>
              <Input
                type="date"
                value={editingTodo.due_date || ''}
                onChange={(e) => setEditingTodo({ ...editingTodo, due_date: e.target.value })}
                className="mt-1"
              />
            </div>

            <div>
              <Label>Category</Label>
              <Input
                value={editingTodo.category || ''}
                onChange={(e) => setEditingTodo({ ...editingTodo, category: e.target.value })}
                placeholder="e.g., work, personal, shopping"
                className="mt-1"
              />
            </div>
          </div>

          <div className="p-4 border-t flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => {
                setIsCreating(false);
                setSelectedTodo(null);
                setEditingTodo({ title: '', description: '', priority: 'medium', status: 'pending', due_date: '', category: '' });
              }}
            >
              Cancel
            </Button>
            <Button
              className="flex-1"
              onClick={handleSave}
              disabled={!editingTodo.title || createMutation.isPending || updateMutation.isPending}
            >
              {isCreating ? 'Create' : 'Save'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
