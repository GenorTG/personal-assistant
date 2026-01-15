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

interface UserProfile {
  id: string;
  name: string;
  about?: string;
  preferences?: string;
}

export default function ProfileSettings({}: any) {
  const { showSuccess, showError } = useToast();
  const queryClient = useQueryClient();
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [editingProfile, setEditingProfile] = useState<Partial<UserProfile>>({
    name: '',
    about: '',
    preferences: '',
  });

  // Fetch user profiles
  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ['user-profiles'],
    queryFn: () => api.listUserProfiles(),
  });

  // Find current profile
  const currentProfile = profiles.find((p: UserProfile) => p.id === selectedProfileId) || profiles[0] || null;

  useEffect(() => {
    if (currentProfile && !selectedProfileId) {
      // Use setTimeout to defer setState and avoid synchronous setState in effect
      const timeoutId = setTimeout(() => {
        setSelectedProfileId(currentProfile.id);
        setEditingProfile(currentProfile);
      }, 0);
      return () => clearTimeout(timeoutId);
    }
    return undefined;
  }, [currentProfile, selectedProfileId]);

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (profile: Partial<UserProfile>) => api.createUserProfile(profile),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['user-profiles'] });
      if (data?.id) {
        setSelectedProfileId(data.id);
        setEditingProfile(data as UserProfile);
        setIsCreating(false);
        showSuccess('User profile created');
      }
    },
    onError: (error: any) => {
      showError(`Failed to create profile: ${error.message}`);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ profileId, profile }: { profileId: string; profile: Partial<UserProfile> }) =>
      api.updateUserProfile(profileId, profile),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-profiles'] });
      showSuccess('User profile updated');
    },
    onError: (error: any) => {
      showError(`Failed to update profile: ${error.message}`);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (profileId: string) => api.deleteUserProfile(profileId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-profiles'] });
      if (selectedProfileId && profiles.length > 1) {
        const remaining = profiles.filter((p: UserProfile) => p.id !== selectedProfileId);
        if (remaining.length > 0) {
          setSelectedProfileId(remaining[0].id);
          setEditingProfile(remaining[0]);
        } else {
          setSelectedProfileId(null);
          setEditingProfile({ name: '', about: '', preferences: '' });
        }
      }
      showSuccess('User profile deleted');
    },
    onError: (error: any) => {
      showError(`Failed to delete profile: ${error.message}`);
    },
  });

  // Set current mutation
  const setCurrentMutation = useMutation({
    mutationFn: (profileId: string) => api.setCurrentUserProfile(profileId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-profiles'] });
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      showSuccess('Current user profile updated');
    },
    onError: (error: any) => {
      showError(`Failed to set current profile: ${error.message}`);
    },
  });

  const handleSelectProfile = (profile: UserProfile) => {
    setSelectedProfileId(profile.id);
    setEditingProfile(profile);
    setIsCreating(false);
  };

  const handleCreateNew = () => {
    setIsCreating(true);
    setSelectedProfileId(null);
    setEditingProfile({ name: '', about: '', preferences: '' });
  };

  const handleSave = () => {
    if (!editingProfile.name) {
      showError('Profile name is required');
      return;
    }

    if (isCreating) {
      createMutation.mutate(editingProfile);
    } else if (selectedProfileId) {
      updateMutation.mutate({ profileId: selectedProfileId, profile: editingProfile });
    }
  };

  const handleDelete = (profileId: string) => {
    if (pendingDeleteId === profileId) {
      // Second click - confirm delete
      deleteMutation.mutate(profileId);
      setPendingDeleteId(null);
    } else {
      // First click - show confirmation state
      setPendingDeleteId(profileId);
      // Reset after 3 seconds if not confirmed
      setTimeout(() => setPendingDeleteId(null), 3000);
    }
  };

  const handleSetCurrent = (profileId: string) => {
    setCurrentMutation.mutate(profileId);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <User size={20} />
          <h4 className="font-semibold">User Profiles</h4>
        </div>
        <Button onClick={handleCreateNew} size="sm" variant="outline">
          <Plus size={16} className="mr-1" />
          New Profile
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Profile List */}
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle className="text-sm">Profiles</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[400px]">
              {isLoading ? (
                <div className="p-4 text-sm text-muted-foreground">Loading...</div>
              ) : profiles.length === 0 ? (
                <div className="p-4 text-sm text-muted-foreground">No profiles yet</div>
              ) : (
                <div className="divide-y">
                  {profiles.map((profile: UserProfile) => (
                    <div
                      key={profile.id}
                      className={`p-3 cursor-pointer hover:bg-muted transition-colors ${
                        selectedProfileId === profile.id ? 'bg-muted border-l-2 border-primary' : ''
                      }`}
                      onClick={() => handleSelectProfile(profile)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-sm truncate">{profile.name || 'Unnamed'}</div>
                          {profile.about && (
                            <div className="text-xs text-muted-foreground truncate mt-1">
                              {profile.about.substring(0, 50)}...
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-1 ml-2">
                          {selectedProfileId === profile.id && (
                            <Check size={14} className="text-primary" />
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSetCurrent(profile.id);
                            }}
                            className="h-6 w-6 p-0"
                            title="Set as current"
                          >
                            <User size={12} />
                          </Button>
                          <Button
                            size="sm"
                            variant={pendingDeleteId === profile.id ? "destructive" : "ghost"}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDelete(profile.id);
                            }}
                            className={cn(
                              "h-6 px-1.5 text-xs",
                              pendingDeleteId === profile.id ? "bg-destructive text-destructive-foreground" : "text-destructive"
                            )}
                            title={pendingDeleteId === profile.id ? "Click again to confirm" : "Delete"}
                          >
                            {pendingDeleteId === profile.id ? "Confirm" : <Trash2 size={12} />}
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

        {/* Profile Editor */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm">
              {isCreating ? 'Create New Profile' : 'Edit Profile'}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label className="block text-sm font-medium mb-1">Your Name *</Label>
              <Input
                type="text"
                value={editingProfile.name || ''}
                onChange={(e) => setEditingProfile({ ...editingProfile, name: e.target.value })}
                className="w-full"
                placeholder="Your name"
              />
            </div>

            <div>
              <Label className="block text-sm font-medium mb-1">About You</Label>
              <Textarea
                value={editingProfile.about || ''}
                onChange={(e) => setEditingProfile({ ...editingProfile, about: e.target.value })}
                className="w-full"
                rows={4}
                placeholder="Tell the assistant about yourself..."
              />
            </div>

            <div>
              <Label className="block text-sm font-medium mb-1">Preferences</Label>
              <Textarea
                value={editingProfile.preferences || ''}
                onChange={(e) => setEditingProfile({ ...editingProfile, preferences: e.target.value })}
                className="w-full"
                rows={3}
                placeholder="Your preferences and interests..."
              />
            </div>

            <Separator />

            <div className="flex gap-2">
              <Button onClick={handleSave} className="flex-1" disabled={!editingProfile.name}>
                {isCreating ? 'Create Profile' : 'Save Changes'}
              </Button>
              {isCreating && (
                <Button
                  onClick={() => {
                    setIsCreating(false);
                    if (currentProfile) {
                      setSelectedProfileId(currentProfile.id);
                      setEditingProfile(currentProfile);
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
