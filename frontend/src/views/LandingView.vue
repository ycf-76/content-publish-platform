<template>
  <div class="lp" @mousemove="onMouseMove">
    <div class="lp-glow lp-glow-1"></div>
    <div class="lp-glow lp-glow-2"></div>
    <div class="lp-glow lp-glow-mouse" ref="mouseGlow"></div>

    <header class="lp-header">
      <div class="lp-header-inner">
        <div class="lp-logo">
          <div class="lp-logo-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
              <path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/>
            </svg>
          </div>
          <span class="lp-logo-text">Pulse Studio</span>
        </div>
        <nav class="lp-nav">
          <a href="#features" class="lp-nav-link">Features</a>
          <a href="#workflow" class="lp-nav-link">Workflow</a>
          <a href="#pricing" class="lp-nav-link">Pricing</a>
          <a href="#faq" class="lp-nav-link">FAQ</a>
        </nav>
        <div class="lp-header-actions">
          <button class="lp-btn-ghost" @click="goToLogin">Sign In</button>
          <button class="lp-btn-primary" @click="goToRegister">Get Started</button>
        </div>
      </div>
    </header>

    <section class="lp-hero">
      <div class="lp-hero-left">
        <div class="lp-hero-badge">
          <span class="lp-hero-badge-dot"></span>
          AI-Powered Content Creation Platform
        </div>
        <h1 class="lp-hero-title font-cal">
          <span class="lp-typewrap" v-for="(line, i) in heroLines" :key="i">
            <span class="lp-typeline" :style="{ animationDelay: i * 0.6 + 's' }">{{ line }}</span>
          </span>
        </h1>
        <p class="lp-hero-desc">
          Multi-agent orchestration for intelligent content production.<br/>
          From insight to publish — one seamless AI workflow.
        </p>
        <div class="lp-hero-actions">
          <button class="lp-btn-primary lp-btn-lg" @click="goToRegister">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>
            Start Free Trial
          </button>
          <button class="lp-btn-outline lp-btn-lg">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>
            Watch Demo
          </button>
        </div>
        <div class="lp-hero-stats">
          <div class="lp-stat">
            <div class="lp-stat-num" data-target="10000" data-suffix="+">0</div>
            <div class="lp-stat-label">Active Creators</div>
          </div>
          <div class="lp-stat-divider"></div>
          <div class="lp-stat">
            <div class="lp-stat-num" data-target="500" data-suffix="万+">0</div>
            <div class="lp-stat-label">Content Generated</div>
          </div>
          <div class="lp-stat-divider"></div>
          <div class="lp-stat">
            <div class="lp-stat-num" data-target="92" data-suffix="%">0</div>
            <div class="lp-stat-label">Efficiency Boost</div>
          </div>
        </div>
      </div>

      <div class="lp-hero-right">
        <div class="lp-orchestration">
          <div class="lp-orch-node" v-for="(node, i) in orchNodes" :key="i"
               :style="{ animationDelay: i * 0.8 + 's' }">
            <div class="lp-orch-dot">
              <div class="lp-orch-pulse"></div>
              <div class="lp-orch-core"></div>
            </div>
            <span class="lp-orch-label">{{ node }}</span>
          </div>
          <svg class="lp-orch-lines" viewBox="0 0 400 300" fill="none">
            <line x1="80" y1="60" x2="200" y2="60" stroke="url(#grad)" stroke-width="1.5" stroke-dasharray="6 4">
              <animate attributeName="stroke-dashoffset" from="0" to="-20" dur="2s" repeatCount="indefinite"/>
            </line>
            <line x1="200" y1="60" x2="320" y2="60" stroke="url(#grad)" stroke-width="1.5" stroke-dasharray="6 4">
              <animate attributeName="stroke-dashoffset" from="0" to="-20" dur="2s" repeatCount="indefinite"/>
            </line>
            <line x1="320" y1="60" x2="320" y2="180" stroke="url(#grad)" stroke-width="1.5" stroke-dasharray="6 4">
              <animate attributeName="stroke-dashoffset" from="0" to="-20" dur="2s" repeatCount="indefinite"/>
            </line>
            <line x1="320" y1="180" x2="200" y2="180" stroke="url(#grad)" stroke-width="1.5" stroke-dasharray="6 4">
              <animate attributeName="stroke-dashoffset" from="0" to="-20" dur="2s" repeatCount="indefinite"/>
            </line>
            <line x1="200" y1="180" x2="80" y2="180" stroke="url(#grad)" stroke-width="1.5" stroke-dasharray="6 4">
              <animate attributeName="stroke-dashoffset" from="0" to="-20" dur="2s" repeatCount="indefinite"/>
            </line>
            <defs>
              <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#f97316" stop-opacity="0.2"/>
                <stop offset="50%" stop-color="#fb923c" stop-opacity="0.8"/>
                <stop offset="100%" stop-color="#f97316" stop-opacity="0.2"/>
              </linearGradient>
            </defs>
          </svg>
          <div class="lp-orch-particles">
            <span v-for="n in 12" :key="n" class="lp-particle"
                  :style="{ animationDelay: n * 0.4 + 's', left: Math.random()*100+'%', top: Math.random()*100+'%' }"></span>
          </div>
        </div>
      </div>
    </section>

    <section id="workflow" class="lp-section lp-workflow">
      <div class="lp-section-header lp-reveal">
        <h2 class="lp-section-title font-cal">How It Flows</h2>
        <p class="lp-section-desc">Five stages, zero friction — from idea to live content</p>
      </div>
      <div class="lp-pipeline lp-reveal">
        <div class="lp-pipe-node" v-for="(step, i) in pipelineSteps" :key="i"
             @mouseenter="activePipe = i" @mouseleave="activePipe = -1">
          <div class="lp-pipe-dot" :class="{ 'lp-pipe-dot-active': activePipe === i }">
            <div class="lp-pipe-ring"></div>
            <div class="lp-pipe-core"></div>
          </div>
          <div class="lp-pipe-info">
            <div class="lp-pipe-name">{{ step.name }}</div>
            <div class="lp-pipe-desc">{{ step.desc }}</div>
          </div>
          <div class="lp-pipe-detail" v-if="activePipe === i">
            <div class="lp-pipe-detail-card">
              <div class="lp-pipe-detail-title">{{ step.name }}</div>
              <p>{{ step.detail }}</p>
            </div>
          </div>
        </div>
        <div class="lp-pipe-line">
          <div class="lp-pipe-flow"></div>
        </div>
      </div>
    </section>

    <section id="features" class="lp-section lp-features">
      <div class="lp-section-header lp-reveal">
        <h2 class="lp-section-title font-cal">Core Capabilities</h2>
        <p class="lp-section-desc">Built for creators who demand more than templates</p>
      </div>
      <div class="lp-features-grid lp-reveal">
        <div class="lp-feat-card lp-feat-wide" @mousemove="onCardTilt" @mouseleave="onCardLeave">
          <div class="lp-feat-icon-wrap" style="--accent: #f97316;">
            <div class="lp-feat-icon-glow"></div>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 0 10 10"/><path d="M12 12l7-7"/><circle cx="12" cy="12" r="3"/></svg>
          </div>
          <h3 class="lp-feat-title">Multi-Agent Orchestration</h3>
          <p class="lp-feat-desc">
            Specialized AI agents collaborate in a directed graph — each node is an expert,
            every edge is a handoff. No monolithic prompts, no hallucination cascades.
          </p>
          <ul class="lp-feat-list">
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> LangGraph state machine</li>
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Conversational execution</li>
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Human-in-the-loop review</li>
          </ul>
        </div>
        <div class="lp-feat-card" @mousemove="onCardTilt" @mouseleave="onCardLeave">
          <div class="lp-feat-icon-wrap" style="--accent: #fb923c;">
            <div class="lp-feat-icon-glow"></div>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v8"/><path d="m4.93 10.93 1.41 1.41"/><path d="M2 18h2"/><path d="M20 18h2"/><path d="m19.07 10.93-1.41 1.41"/><path d="M22 22H2"/><path d="m16 6-4-4-4 4"/><path d="m16 18-4 4-4-4"/></svg>
          </div>
          <h3 class="lp-feat-title">Plugin Architecture</h3>
          <p class="lp-feat-desc">
            Every node is replaceable. Swap the copywriter, plug in your own image model,
            or build entirely new node types — the registry handles it.
          </p>
          <ul class="lp-feat-list">
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Node & Skill registries</li>
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Token-budgeted LLM access</li>
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> ZIP-based plugin packages</li>
          </ul>
        </div>
        <div class="lp-feat-card" @mousemove="onCardTilt" @mouseleave="onCardLeave">
          <div class="lp-feat-icon-wrap" style="--accent: #A78BFA;">
            <div class="lp-feat-icon-glow"></div>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v4"/><path d="M12 19v4"/><path d="M1 12h4"/><path d="M19 12h4"/><path d="m4.2 4.2 2.9 2.9"/><path d="m16.9 16.9 2.9 2.9"/><path d="m4.2 19.8 2.9-2.9"/><path d="m16.9 7.1 2.9-2.9"/></svg>
          </div>
          <h3 class="lp-feat-title">Dynamic Workflow</h3>
          <p class="lp-feat-desc">
            Drag, drop, connect — build custom pipelines in the visual editor.
            Topological sort ensures correct execution order automatically.
          </p>
          <ul class="lp-feat-list">
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Visual DAG editor</li>
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Auto topological sort</li>
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Save & reuse templates</li>
          </ul>
        </div>
        <div class="lp-feat-card" @mousemove="onCardTilt" @mouseleave="onCardLeave">
          <div class="lp-feat-icon-wrap" style="--accent: var(--color-accent);">
            <div class="lp-feat-icon-glow"></div>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          </div>
          <h3 class="lp-feat-title">Conversational Execution</h3>
          <p class="lp-feat-desc">
            The workflow pauses when it needs you. Review, redirect, approve —
            chat with your AI agents like a creative director briefing a team.
          </p>
          <ul class="lp-feat-list">
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Suspend & resume nodes</li>
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Real-time SSE events</li>
            <li><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Chat-based feedback loop</li>
          </ul>
        </div>
      </div>
    </section>

    <section id="pricing" class="lp-section lp-pricing">
      <div class="lp-section-header lp-reveal">
        <h2 class="lp-section-title font-cal">Simple Pricing</h2>
        <p class="lp-section-desc">Start free, scale when ready</p>
      </div>
      <div class="lp-pricing-grid lp-reveal">
        <div class="lp-price-card">
          <div class="lp-price-head">
            <h3 class="lp-price-name">Starter</h3>
            <p class="lp-price-desc">For individual creators</p>
          </div>
          <div class="lp-price-amount">
            <span class="lp-price-currency">¥</span>
            <span class="lp-price-val" data-target="0">0</span>
            <span class="lp-price-period">/mo</span>
          </div>
          <ul class="lp-price-features">
            <li>10 workflow runs / month</li>
            <li>Basic trend tracking</li>
            <li>Standard image gen</li>
            <li>Basic copywriting</li>
            <li class="lp-price-off">Batch operations</li>
            <li class="lp-price-off">Scheduled publish</li>
          </ul>
          <button class="lp-btn-outline lp-price-cta" @click="goToRegister">Get Started</button>
        </div>
        <div class="lp-price-card lp-price-popular">
          <div class="lp-price-badge">Most Popular</div>
          <div class="lp-price-head">
            <h3 class="lp-price-name">Pro</h3>
            <p class="lp-price-desc">For full-time creators</p>
          </div>
          <div class="lp-price-amount">
            <span class="lp-price-currency">¥</span>
            <span class="lp-price-val" data-target="299">0</span>
            <span class="lp-price-period">/mo</span>
          </div>
          <ul class="lp-price-features">
            <li>100 workflow runs / month</li>
            <li>Advanced trend analysis</li>
            <li>HD image generation</li>
            <li>Multi-style copywriting</li>
            <li>Batch operations</li>
            <li>Scheduled publish</li>
          </ul>
          <button class="lp-btn-primary lp-price-cta" @click="goToRegister">Subscribe Now</button>
        </div>
        <div class="lp-price-card">
          <div class="lp-price-head">
            <h3 class="lp-price-name">Team</h3>
            <p class="lp-price-desc">For agencies & teams</p>
          </div>
          <div class="lp-price-amount">
            <span class="lp-price-currency">¥</span>
            <span class="lp-price-val" data-target="999">0</span>
            <span class="lp-price-period">/mo</span>
          </div>
          <ul class="lp-price-features">
            <li>Unlimited workflows</li>
            <li>Full trend suite</li>
            <li>4K image generation</li>
            <li>Team collaboration</li>
            <li>Analytics dashboard</li>
            <li>Dedicated support</li>
          </ul>
          <button class="lp-btn-outline lp-price-cta" @click="goToRegister">Contact Sales</button>
        </div>
      </div>
    </section>

    <section id="faq" class="lp-section lp-faq">
      <div class="lp-section-header lp-reveal">
        <h2 class="lp-section-title font-cal">FAQ</h2>
        <p class="lp-section-desc">Quick answers to common questions</p>
      </div>
      <div class="lp-faq-list lp-reveal">
        <div class="lp-faq-item" :class="{ 'lp-faq-open': activeFaq === i }"
             v-for="(faq, i) in faqs" :key="i" @click="toggleFaq(i)">
          <div class="lp-faq-q">
            <span>{{ faq.q }}</span>
            <span class="lp-faq-icon">{{ activeFaq === i ? '−' : '+' }}</span>
          </div>
          <div class="lp-faq-a" v-show="activeFaq === i">{{ faq.a }}</div>
        </div>
      </div>
    </section>

    <section class="lp-cta-section">
      <div class="lp-cta-box lp-reveal">
        <h2 class="lp-cta-title font-cal">Ready to 10x your content pipeline?</h2>
        <p class="lp-cta-desc">Start creating with AI agents today — no credit card required.</p>
        <div class="lp-cta-actions">
          <button class="lp-btn-primary lp-btn-lg" @click="goToRegister">Start Free Trial</button>
          <button class="lp-btn-outline lp-btn-lg">Talk to Us</button>
        </div>
      </div>
    </section>

    <footer class="lp-footer">
      <div class="lp-footer-inner">
        <div class="lp-footer-brand">
          <div class="lp-logo">
            <div class="lp-logo-icon lp-logo-icon-sm">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
                <path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/>
              </svg>
            </div>
            <span class="lp-logo-text">Pulse Studio</span>
          </div>
          <p class="lp-footer-tagline">Intelligent content creation, orchestrated.</p>
        </div>
        <div class="lp-footer-links">
          <div class="lp-footer-col">
            <h4>Product</h4>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#workflow">Workflow</a>
          </div>
          <div class="lp-footer-col">
            <h4>Resources</h4>
            <a href="#">Documentation</a>
            <a href="#">API Reference</a>
            <a href="#">Blog</a>
          </div>
          <div class="lp-footer-col">
            <h4>Company</h4>
            <a href="#">About</a>
            <a href="#">Careers</a>
            <a href="#">Contact</a>
          </div>
        </div>
      </div>
      <div class="lp-footer-bottom">
        <p>&copy; 2026 Pulse Studio. All rights reserved.</p>
        <div class="lp-footer-legal">
          <a href="#">Privacy</a>
          <a href="#">Terms</a>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const activeFaq = ref<number | null>(null)
const activePipe = ref(-1)
const mouseGlow = ref<HTMLElement | null>(null)

const heroLines = ['Create with', 'Intelligence']
const orchNodes = ['Insight', 'Create', 'Compose', 'Review', 'Publish']

const pipelineSteps = [
  { name: 'Insight', desc: 'Trend discovery', detail: 'AI agents scan trending topics, analyze competition, and recommend high-potential angles for your content.' },
  { name: 'Create', desc: 'Visual generation', detail: 'Generate platform-optimized images with state-of-the-art diffusion models. Multiple styles, batch output, smart cropping.' },
  { name: 'Compose', desc: 'AI copywriting', detail: 'Multi-style copywriting that adapts to your voice. Headlines, body copy, hashtags — generated and refined in seconds.' },
  { name: 'Review', desc: 'Quality & compliance', detail: 'Automated compliance checks, sensitivity scoring, and quality rating before anything goes live.' },
  { name: 'Publish', desc: 'One-click live', detail: 'Schedule or publish instantly. Cross-platform support with platform-specific formatting built in.' },
]

const faqs = [
  { q: 'Who is Pulse Studio for?', a: 'Any content creator — individual bloggers, MCN agencies, brand marketing teams. If you produce content at scale, Pulse Studio is for you.' },
  { q: 'Will AI-generated content get flagged?', a: 'No. Every piece goes through built-in compliance checks and sensitivity filters. We also recommend human review at the final stage for 100% safety.' },
  { q: 'Which AI models are supported?', a: 'GPT-4o, Claude 3.5, DeepSeek, Qwen for text; FLUX.1 Pro, SD3, Midjourney for images. You choose — or let the smart router decide.' },
  { q: 'Is my data secure?', a: 'Enterprise-grade encryption for all data in transit and at rest. Account credentials use isolated encrypted channels. We never operate your accounts without explicit confirmation.' },
]

function goToLogin() { router.push('/login?force=true') }
function goToRegister() { router.push('/login?register=true&force=true') }
function toggleFaq(i: number) { activeFaq.value = activeFaq.value === i ? null : i }

function onMouseMove(e: MouseEvent) {
  if (!mouseGlow.value) return
  mouseGlow.value.style.left = e.clientX + 'px'
  mouseGlow.value.style.top = e.clientY + 'px'
}

function onCardTilt(e: MouseEvent) {
  const card = e.currentTarget as HTMLElement
  const rect = card.getBoundingClientRect()
  const x = (e.clientX - rect.left) / rect.width - 0.5
  const y = (e.clientY - rect.top) / rect.height - 0.5
  card.style.transform = `perspective(800px) rotateY(${x * 8}deg) rotateX(${-y * 8}deg) scale(1.02)`
}

function onCardLeave(e: MouseEvent) {
  const card = e.currentTarget as HTMLElement
  card.style.transform = ''
}

let observer: IntersectionObserver | null = null

function animateCounters() {
  document.querySelectorAll<HTMLElement>('.lp-stat-num, .lp-price-val').forEach(el => {
    const target = parseInt(el.dataset.target || '0')
    const suffix = el.dataset.suffix || ''
    const duration = 1500
    const start = performance.now()
    function tick(now: number) {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      const current = Math.round(target * eased)
      el.textContent = current.toLocaleString() + suffix
      if (progress < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })
}

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('lp-visible')
        if (entry.target.querySelector('.lp-stat-num') || entry.target.querySelector('.lp-price-val')) {
          animateCounters()
        }
      }
    })
  }, { threshold: 0.15 })

  document.querySelectorAll('.lp-reveal').forEach(el => observer?.observe(el))

  const heroEl = document.querySelector('.lp-hero')
  if (heroEl) observer?.observe(heroEl)
})

onUnmounted(() => { observer?.disconnect() })
</script>

<style scoped>
.lp {
  --bg: #0A0A0B;
  --card: rgba(255,255,255,0.04);
  --card-hover: rgba(255,255,255,0.07);
  --border: rgba(255,255,255,0.08);
  --border-hover: rgba(255,255,255,0.15);
  --text: #F9FAFB;
  --text2: #9CA3AF;
  --text3: #6B7280;
  --accent: #FF2442;
  --accent2: #FF4D66;
  --accent-deep: #E01D3A;
  --accent-soft: rgba(255,36,66,0.3);
  --grad: linear-gradient(135deg, #FF2442, #FF4D66);

  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  overflow-x: hidden;
  position: relative;
}

.lp-glow {
  position: fixed;
  border-radius: 50%;
  pointer-events: none;
  z-index: 0;
  filter: blur(120px);
}
.lp-glow-1 {
  width: 600px; height: 600px;
  background: rgba(249,115,22,0.10);
  top: -200px; left: -100px;
  animation: glowDrift1 12s ease-in-out infinite;
}
.lp-glow-2 {
  width: 500px; height: 500px;
  background: rgba(251,146,60,0.08);
  bottom: -150px; right: -100px;
  animation: glowDrift2 14s ease-in-out infinite;
}
.lp-glow-mouse {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(249,115,22,0.06) 0%, transparent 70%);
  transform: translate(-50%, -50%);
  transition: left 0.3s ease-out, top 0.3s ease-out;
}
@keyframes glowDrift1 {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(80px, 60px); }
}
@keyframes glowDrift2 {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(-60px, -80px); }
}

.lp-header {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 100;
  padding: 14px 40px;
  background: rgba(10,10,11,0.7);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border);
}
.lp-header-inner {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.lp-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}
.lp-logo-icon {
  width: 36px; height: 36px;
  border-radius: 10px;
  background: var(--grad);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 0 20px rgba(255,36,66,0.3);
}
.lp-logo-icon-sm { width: 28px; height: 28px; border-radius: 8px; }
.lp-logo-text {
  font-family: var(--font-display);
  font-size: var(--text-h2);
  font-weight: var(--weight-bold);
  color: var(--text);
  letter-spacing: 0.5px;
}
.lp-nav { display: flex; gap: 28px; }
.lp-nav-link {
  font-size: 14px;
  color: var(--text2);
  text-decoration: none;
  transition: color 0.2s;
}
.lp-nav-link:hover { color: var(--text); }
.lp-header-actions { display: flex; gap: 10px; }

.lp-btn-primary {
  padding: 8px 20px;
  border-radius: 8px;
  border: none;
  background: var(--grad);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 0 20px rgba(249,115,22,0.2);
}
.lp-btn-primary:hover {
  box-shadow: 0 0 30px rgba(249,115,22,0.4);
  transform: translateY(-1px);
}
.lp-btn-outline {
  padding: 8px 20px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.lp-btn-outline:hover {
  border-color: var(--border-hover);
  background: var(--card);
}
.lp-btn-ghost {
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--text2);
  font-size: 14px;
  cursor: pointer;
  transition: color 0.2s;
}
.lp-btn-ghost:hover { color: var(--text); }
.lp-btn-lg { padding: 12px 28px; font-size: var(--text-body); }

.lp-hero {
  max-width: 1280px;
  margin: 0 auto;
  padding: 140px 40px 100px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 60px;
  align-items: center;
  position: relative;
  z-index: 1;
}
.lp-hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 9999px;
  border: 1px solid var(--border);
  background: var(--card);
  font-size: 13px;
  color: var(--accent2);
  margin-bottom: 28px;
}
.lp-hero-badge-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--accent2);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(249,115,22,0.4); }
  50% { opacity: 0.7; box-shadow: 0 0 0 6px rgba(249,115,22,0); }
}
.lp-hero-title {
  font-size: 60px;
  line-height: 1.08;
  margin-bottom: 24px;
}
.lp-typewrap {
  display: block;
  overflow: hidden;
}
.lp-typeline {
  display: block;
  transform: translateY(110%);
  animation: typeSlide 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
@keyframes typeSlide {
  to { transform: translateY(0); }
}
.lp-hero-desc {
  font-size: 17px;
  color: var(--text2);
  line-height: 1.7;
  margin-bottom: 36px;
}
.lp-hero-actions { display: flex; gap: 14px; margin-bottom: 56px; }
.lp-hero-stats {
  display: flex;
  align-items: center;
  gap: 28px;
}
.lp-stat-num {
  font-size: 28px;
  font-weight: 700;
  background: var(--grad);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.lp-stat-label { font-size: 13px; color: var(--text3); margin-top: 4px; }
.lp-stat-divider { width: 1px; height: 36px; background: var(--border); }

.lp-hero-right {
  display: flex;
  justify-content: center;
  align-items: center;
}
.lp-orchestration {
  position: relative;
  width: 400px;
  height: 280px;
}
.lp-orch-node {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  opacity: 0;
  animation: orchFadeIn 0.6s ease forwards;
}
.lp-orch-node:nth-child(1) { left: 40px; top: 30px; }
.lp-orch-node:nth-child(2) { left: 160px; top: 30px; }
.lp-orch-node:nth-child(3) { left: 280px; top: 30px; }
.lp-orch-node:nth-child(4) { left: 280px; top: 150px; }
.lp-orch-node:nth-child(5) { left: 160px; top: 150px; }
@keyframes orchFadeIn { to { opacity: 1; } }
.lp-orch-dot {
  position: relative;
  width: 16px; height: 16px;
}
.lp-orch-pulse {
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  background: rgba(249,115,22,0.2);
  animation: orchPulse 2.5s ease-in-out infinite;
}
@keyframes orchPulse {
  0%, 100% { transform: scale(1); opacity: 0.5; }
  50% { transform: scale(1.8); opacity: 0; }
}
.lp-orch-core {
  width: 16px; height: 16px;
  border-radius: 50%;
  background: var(--grad);
  box-shadow: 0 0 12px rgba(249,115,22,0.5);
}
.lp-orch-label {
  font-size: 11px;
  color: var(--text2);
  font-weight: 500;
  letter-spacing: 0.5px;
}
.lp-orch-lines {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.lp-orch-particles {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.lp-particle {
  position: absolute;
  width: 2px; height: 2px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0;
  animation: particleFly 4s linear infinite;
}
@keyframes particleFly {
  0% { opacity: 0; transform: translate(0, 0) scale(0); }
  20% { opacity: 0.6; transform: scale(1); }
  80% { opacity: 0.3; }
  100% { opacity: 0; transform: translate(var(--dx, 30px), var(--dy, -20px)) scale(0); }
}

.lp-section {
  max-width: 1280px;
  margin: 0 auto;
  padding: 100px 40px;
  position: relative;
  z-index: 1;
}
.lp-section-header { text-align: center; margin-bottom: 64px; }
.lp-section-title {
  font-size: 44px;
  margin-bottom: 12px;
  background: var(--grad);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.lp-section-desc { font-size: 17px; color: var(--text2); }

.lp-reveal {
  opacity: 0;
  transform: translateY(30px);
  transition: opacity 0.7s ease, transform 0.7s ease;
}
.lp-reveal.lp-visible {
  opacity: 1;
  transform: translateY(0);
}

.lp-pipeline {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 40px 0;
}
.lp-pipe-line {
  position: absolute;
  top: 55px;
  left: 60px;
  right: 60px;
  height: 2px;
  background: var(--border);
  overflow: hidden;
}
.lp-pipe-flow {
  width: 60px;
  height: 100%;
  background: var(--grad);
  animation: pipeFlow 3s linear infinite;
}
@keyframes pipeFlow {
  0% { transform: translateX(-60px); }
  100% { transform: translateX(calc(100% + 60px)); }
}
.lp-pipe-node {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  z-index: 2;
  cursor: pointer;
}
.lp-pipe-dot {
  position: relative;
  width: 28px; height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.lp-pipe-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid var(--border);
  transition: all 0.3s;
}
.lp-pipe-dot-active .lp-pipe-ring {
  border-color: var(--accent);
  box-shadow: 0 0 16px rgba(249,115,22,0.4);
}
.lp-pipe-core {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--text3);
  transition: all 0.3s;
}
.lp-pipe-dot-active .lp-pipe-core {
  background: var(--grad);
  box-shadow: 0 0 10px rgba(249,115,22,0.6);
}
.lp-pipe-info { text-align: center; }
.lp-pipe-name {
  font-size: 14px;
  font-weight: var(--weight-semibold);
  color: var(--text);
  margin-bottom: 2px;
}
.lp-pipe-desc { font-size: 12px; color: var(--text3); }
.lp-pipe-detail {
  position: absolute;
  top: 100%;
  margin-top: 12px;
  left: 50%;
  transform: translateX(-50%);
  width: 240px;
  z-index: 10;
}
.lp-pipe-detail-card {
  padding: 16px;
  border-radius: 12px;
  background: rgba(20,20,22,0.95);
  border: 1px solid var(--border-hover);
  backdrop-filter: blur(12px);
}
.lp-pipe-detail-title {
  font-size: 14px;
  font-weight: var(--weight-semibold);
  color: var(--accent);
  margin-bottom: 6px;
}
.lp-pipe-detail-card p {
  font-size: 13px;
  color: var(--text2);
  line-height: 1.5;
}

.lp-features-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}
.lp-feat-card {
  padding: 32px;
  border-radius: 16px;
  background: var(--card);
  border: 1px solid var(--border);
  transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;
  will-change: transform;
}
.lp-feat-card:hover {
  border-color: var(--border-hover);
  box-shadow: 0 8px 40px rgba(249,115,22,0.08);
}
.lp-feat-wide { grid-column: span 2; }
.lp-feat-icon-wrap {
  position: relative;
  width: 48px; height: 48px;
  border-radius: 12px;
  background: rgba(249,115,22,0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  margin-bottom: 20px;
}
.lp-feat-icon-glow {
  position: absolute;
  inset: -4px;
  border-radius: 16px;
  background: var(--accent);
  opacity: 0;
  filter: blur(12px);
  transition: opacity 0.3s;
}
.lp-feat-card:hover .lp-feat-icon-glow { opacity: 0.15; }
.lp-feat-title {
  font-size: 20px;
  font-weight: var(--weight-semibold);
  color: var(--text);
  margin-bottom: 10px;
}
.lp-feat-desc {
  font-size: 14px;
  color: var(--text2);
  line-height: 1.6;
  margin-bottom: 18px;
}
.lp-feat-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.lp-feat-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text2);
}
.lp-feat-list li svg { color: var(--accent2); flex-shrink: 0; }

.lp-pricing-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.lp-price-card {
  padding: 32px;
  border-radius: 16px;
  background: var(--card);
  border: 1px solid var(--border);
  position: relative;
  transition: all 0.3s;
}
.lp-price-card:hover {
  border-color: var(--border-hover);
  transform: translateY(-4px);
}
.lp-price-popular {
  border-color: var(--accent);
  animation: popularFloat 4s ease-in-out infinite;
}
@keyframes popularFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}
.lp-price-popular:hover { animation: none; transform: translateY(-4px); }
.lp-price-badge {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 14px;
  border-radius: 9999px;
  background: var(--grad);
  color: #fff;
  font-size: 11px;
  font-weight: var(--weight-semibold);
}
.lp-price-head { text-align: center; margin-bottom: 20px; }
.lp-price-name { font-size: var(--text-h1); font-weight: var(--weight-semibold); color: var(--text); margin-bottom: 4px; }
.lp-price-desc { font-size: 13px; color: var(--text3); }
.lp-price-amount { text-align: center; margin-bottom: 28px; }
.lp-price-currency { font-size: 20px; font-weight: var(--weight-semibold); color: var(--accent); }
.lp-price-val { font-size: 44px; font-weight: 700; color: var(--accent); }
.lp-price-period { font-size: 14px; color: var(--text3); }
.lp-price-features {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 28px;
}
.lp-price-features li {
  font-size: 14px;
  color: var(--text2);
  padding-left: 20px;
  position: relative;
}
.lp-price-features li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 7px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: rgba(249,115,22,0.2);
  border: 1.5px solid var(--accent);
}
.lp-price-off {
  color: var(--text3) !important;
  text-decoration: line-through;
}
.lp-price-off::before {
  background: var(--border) !important;
  border-color: var(--text3) !important;
}
.lp-price-cta {
  width: 100%;
  justify-content: center;
  padding: 10px;
}

.lp-faq-list {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.lp-faq-item {
  padding: 18px 22px;
  border-radius: 12px;
  background: var(--card);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: all 0.2s;
}
.lp-faq-item:hover { border-color: var(--border-hover); }
.lp-faq-open { border-color: var(--accent) !important; }
.lp-faq-q {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--text);
}
.lp-faq-icon {
  font-size: 18px;
  color: var(--accent);
  width: 24px;
  text-align: center;
}
.lp-faq-a {
  margin-top: 14px;
  font-size: 14px;
  color: var(--text2);
  line-height: 1.7;
}

.lp-cta-section {
  max-width: 1280px;
  margin: 0 auto;
  padding: 60px 40px 100px;
  position: relative;
  z-index: 1;
}
.lp-cta-box {
  padding: 64px;
  border-radius: 20px;
  background: var(--card);
  border: 1px solid var(--border);
  text-align: center;
  position: relative;
  overflow: hidden;
}
.lp-cta-box::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at 50% 0%, rgba(249,115,22,0.08) 0%, transparent 60%);
  pointer-events: none;
}
.lp-cta-title {
  font-size: 40px;
  margin-bottom: 12px;
  position: relative;
}
.lp-cta-desc {
  font-size: 17px;
  color: var(--text2);
  margin-bottom: 32px;
  position: relative;
}
.lp-cta-actions {
  display: flex;
  gap: 14px;
  justify-content: center;
  position: relative;
}

.lp-footer {
  padding: 48px 40px 28px;
  border-top: 1px solid var(--border);
  position: relative;
  z-index: 1;
}
.lp-footer-inner {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  margin-bottom: 36px;
}
.lp-footer-tagline { font-size: 13px; color: var(--text3); margin-top: 8px; }
.lp-footer-links { display: flex; gap: 64px; }
.lp-footer-col h4 {
  font-size: 13px;
  font-weight: var(--weight-semibold);
  color: var(--text);
  margin-bottom: 14px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.lp-footer-col a {
  display: block;
  font-size: 13px;
  color: var(--text3);
  text-decoration: none;
  margin-bottom: 10px;
  transition: color 0.2s;
}
.lp-footer-col a:hover { color: var(--text); }
.lp-footer-bottom {
  max-width: 1280px;
  margin: 0 auto;
  padding-top: 24px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.lp-footer-bottom p { font-size: 12px; color: var(--text3); }
.lp-footer-legal { display: flex; gap: 20px; }
.lp-footer-legal a {
  font-size: 12px;
  color: var(--text3);
  text-decoration: none;
  transition: color 0.2s;
}
.lp-footer-legal a:hover { color: var(--text); }

@media (max-width: 1024px) {
  .lp-hero {
    grid-template-columns: 1fr;
    padding: 120px 20px 60px;
  }
  .lp-hero-right { display: none; }
  .lp-features-grid { grid-template-columns: 1fr; }
  .lp-feat-wide { grid-column: span 1; }
  .lp-pricing-grid { grid-template-columns: 1fr; }
  .lp-nav { display: none; }
  .lp-pipeline { flex-wrap: wrap; gap: 20px; justify-content: center; }
  .lp-pipe-line { display: none; }
  .lp-hero-title { font-size: 40px; }
  .lp-section-title { font-size: 32px; }
  .lp-footer-inner { flex-direction: column; gap: 32px; }
}
</style>