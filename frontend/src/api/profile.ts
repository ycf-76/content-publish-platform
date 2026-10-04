import apiClient from './client'

export type PrimaryDomain =
  | 'tech' | 'beauty' | 'food' | 'travel' | 'education'
  | 'parenting' | 'fitness' | 'finance' | 'other'

export type CreatorTone = 'professional' | 'friendly' | 'lively' | 'serious' | 'humorous'

export type VisualStyle = 'warm' | 'cool' | 'minimal' | 'rich'

export interface UserProfile {
  primary_domain: PrimaryDomain
  sub_domain: string | null
  tone: CreatorTone
  visual_style: VisualStyle
  taboo_topics: string[]
  taboo_words: string[]
  identity: string | null
  differentiation: string | null
  content_direction: string | null
  target_audience: string | null
  audience_pain_points: string | null
  opening_style: string | null
  content_rhythm: string | null
  signature_elements: string | null
}

export interface UpdateProfileRequest {
  primary_domain: PrimaryDomain
  sub_domain?: string | null
  tone?: CreatorTone
  visual_style?: VisualStyle
  taboo_topics?: string[]
  taboo_words?: string[]
  identity?: string | null
  differentiation?: string | null
  content_direction?: string | null
  target_audience?: string | null
  audience_pain_points?: string | null
  opening_style?: string | null
  content_rhythm?: string | null
  signature_elements?: string | null
}

export interface ProfileValidationResponse {
  valid: boolean
  reason: string | null
  profile: UserProfile | null
}

export const profileApi = {
  async get(): Promise<UserProfile | null> {
    const data = await apiClient.get('/profile') as any
    if (data && data.primary_domain) return data as UserProfile
    return null
  },

  async update(req: UpdateProfileRequest): Promise<UserProfile> {
    const data = await apiClient.put('/profile', req) as any
    return data as UserProfile
  },

  async validate(): Promise<ProfileValidationResponse> {
    const data = await apiClient.post('/profile/validate') as any
    return data as ProfileValidationResponse
  },
}