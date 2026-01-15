'use client';

import { useState, useEffect } from 'react';
import { User, Plus, Trash2, Check, X } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';

interface CharacterCard {
  id: string;
  name: string;
  personality?: string;
  background?: string;
  instructions?: string;
}

export default function CharacterSettings({}: any) {
  const { showSuccess, showError } = useToast();
  const queryClient = useQueryClient();
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [editingCard, setEditingCard] = useState<Partial<CharacterCard>>({
    name: '',
    personality: '',
    background: '',
    instructions: '',
  });

  // Fetch character cards
  const { data: cards = [], isLoading } = useQuery({
    queryKey: ['character-cards'],
    queryFn: () => api.listCharacterCards(),
  });

  // Find current card
  const currentCard = cards.find((c: CharacterCard) => c.id === selectedCardId) || cards[0] || null;

  useEffect(() => {
    if (currentCard && !selectedCardId) {
      // Use setTimeout to defer setState and avoid synchronous setState in effect
      const timeoutId = setTimeout(() => {
        setSelectedCardId(currentCard.id);
        setEditingCard(currentCard);
      }, 0);
      return () => clearTimeout(timeoutId);
    }
    return undefined;
  }, [currentCard, selectedCardId]);

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (card: Partial<CharacterCard>) => api.createCharacterCard(card),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['character-cards'] });
      if (data?.id) {
        setSelectedCardId(data.id);
        setEditingCard(data as CharacterCard);
        setIsCreating(false);
        showSuccess('Character card created');
      }
    },
    onError: (error: any) => {
      showError(`Failed to create character: ${error.message}`);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ cardId, card }: { cardId: string; card: Partial<CharacterCard> }) =>
      api.updateCharacterCard(cardId, card),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character-cards'] });
      showSuccess('Character card updated');
    },
    onError: (error: any) => {
      showError(`Failed to update character: ${error.message}`);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (cardId: string) => api.deleteCharacterCard(cardId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character-cards'] });
      if (selectedCardId && cards.length > 1) {
        const remaining = cards.filter((c: CharacterCard) => c.id !== selectedCardId);
        if (remaining.length > 0) {
          setSelectedCardId(remaining[0].id);
          setEditingCard(remaining[0]);
        } else {
          setSelectedCardId(null);
          setEditingCard({ name: '', personality: '', background: '', instructions: '' });
        }
      }
      showSuccess('Character card deleted');
    },
    onError: (error: any) => {
      showError(`Failed to delete character: ${error.message}`);
    },
  });

  // Set current mutation
  const setCurrentMutation = useMutation({
    mutationFn: (cardId: string) => api.setCurrentCharacterCard(cardId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character-cards'] });
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      showSuccess('Current character card updated');
    },
    onError: (error: any) => {
      showError(`Failed to set current character: ${error.message}`);
    },
  });

  const handleSelectCard = (card: CharacterCard) => {
    setSelectedCardId(card.id);
    setEditingCard(card);
    setIsCreating(false);
  };

  const handleCreateNew = () => {
    setIsCreating(true);
    setSelectedCardId(null);
    setEditingCard({ name: '', personality: '', background: '', instructions: '' });
  };

  const handleSave = () => {
    if (!editingCard.name) {
      showError('Character name is required');
      return;
    }

    if (isCreating) {
      createMutation.mutate(editingCard);
    } else if (selectedCardId) {
      updateMutation.mutate({ cardId: selectedCardId, card: editingCard });
    }
  };

  const handleDelete = (cardId: string) => {
    if (pendingDeleteId === cardId) {
      // Second click - confirm delete
      deleteMutation.mutate(cardId);
      setPendingDeleteId(null);
    } else {
      // First click - show confirmation state
      setPendingDeleteId(cardId);
      // Reset after 3 seconds if not confirmed
      setTimeout(() => setPendingDeleteId(null), 3000);
    }
  };

  const handleSetCurrent = (cardId: string) => {
    setCurrentMutation.mutate(cardId);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <User size={20} />
          <h4 className="font-semibold">Character Cards</h4>
        </div>
        <Button onClick={handleCreateNew} size="sm" variant="outline">
          <Plus size={16} className="mr-1" />
          New Character
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Character List */}
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle className="text-sm">Characters</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[400px]">
              {isLoading ? (
                <div className="p-4 text-sm text-muted-foreground">Loading...</div>
              ) : cards.length === 0 ? (
                <div className="p-4 text-sm text-muted-foreground">No characters yet</div>
              ) : (
                <div className="divide-y">
                  {cards.map((card: CharacterCard) => (
                    <div
                      key={card.id}
                      className={`p-3 cursor-pointer hover:bg-muted transition-colors ${
                        selectedCardId === card.id ? 'bg-muted border-l-2 border-primary' : ''
                      }`}
                      onClick={() => handleSelectCard(card)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-sm truncate">{card.name || 'Unnamed'}</div>
                          {card.personality && (
                            <div className="text-xs text-muted-foreground truncate mt-1">
                              {card.personality.substring(0, 50)}...
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-1 ml-2">
                          {selectedCardId === card.id && (
                            <Check size={14} className="text-primary" />
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSetCurrent(card.id);
                            }}
                            className="h-6 w-6 p-0"
                            title="Set as current"
                          >
                            <User size={12} />
                          </Button>
                          <Button
                            size="sm"
                            variant={pendingDeleteId === card.id ? "destructive" : "ghost"}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDelete(card.id);
                            }}
                            className={cn(
                              "h-6 px-1.5 text-xs",
                              pendingDeleteId === card.id ? "bg-destructive text-destructive-foreground" : "text-destructive"
                            )}
                            title={pendingDeleteId === card.id ? "Click again to confirm" : "Delete"}
                          >
                            {pendingDeleteId === card.id ? "Confirm" : <Trash2 size={12} />}
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Character Editor */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm">
              {isCreating ? 'Create New Character' : 'Edit Character'}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label className="block text-sm font-medium mb-1">Name *</Label>
              <Input
                type="text"
                value={editingCard.name || ''}
                onChange={(e) => setEditingCard({ ...editingCard, name: e.target.value })}
                className="w-full"
                placeholder="Character name"
              />
            </div>

            <div>
              <Label className="block text-sm font-medium mb-1">Personality</Label>
              <Textarea
                value={editingCard.personality || ''}
                onChange={(e) => setEditingCard({ ...editingCard, personality: e.target.value })}
                className="w-full"
                rows={4}
                placeholder="Describe the character's personality, traits, and behavior..."
              />
            </div>

            <div>
              <Label className="block text-sm font-medium mb-1">Background</Label>
              <Textarea
                value={editingCard.background || ''}
                onChange={(e) => setEditingCard({ ...editingCard, background: e.target.value })}
                className="w-full"
                rows={3}
                placeholder="Character background and history..."
              />
            </div>

            <div>
              <Label className="block text-sm font-medium mb-1">Instructions</Label>
              <Textarea
                value={editingCard.instructions || ''}
                onChange={(e) => setEditingCard({ ...editingCard, instructions: e.target.value })}
                className="w-full"
                rows={3}
                placeholder="Additional instructions for behavior..."
              />
            </div>

            <Separator />

            <div className="flex gap-2">
              <Button onClick={handleSave} className="flex-1" disabled={!editingCard.name}>
                {isCreating ? 'Create Character' : 'Save Changes'}
              </Button>
              {isCreating && (
                <Button
                  onClick={() => {
                    setIsCreating(false);
                    if (currentCard) {
                      setSelectedCardId(currentCard.id);
                      setEditingCard(currentCard);
                    }
                  }}
                  variant="outline"
                >
                  <X size={16} className="mr-1" />
                  Cancel
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
