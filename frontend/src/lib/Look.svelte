<script lang="ts">
  import { app } from './app.svelte';
  import Label from './Label.svelte';
  import type { Verdict } from './types';

  let { active }: { active: boolean } = $props();

  const piece = $derived(app.current);
  const THRESHOLD = 90;

  let leaving = $state<Verdict | null>(null);
  let dx = $state(0);
  let dragging = $state(false);
  let loaded = $state(false);
  let broken = $state(false);
  /** Phone only: the label, shown on demand. Stays open across pieces until closed. */
  let info = $state(false);
  let startX = 0;
  let startY = 0;
  let onArt = false;

  // A new piece on the wall starts unloaded, whatever happened to the last one.
  $effect(() => {
    void piece?.key;
    loaded = false;
    broken = false;
  });

  const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function decide(verdict: Verdict) {
    if (!piece || leaving) return;
    leaving = verdict;
    setTimeout(
      () => {
        app.decide(verdict);
        leaving = null;
        dx = 0;
      },
      reduced() ? 0 : verdict === 'keep' ? 460 : 300
    );
  }

  function onKey(event: KeyboardEvent) {
    if (!active || event.metaKey || event.ctrlKey || event.altKey) return;
    if (document.querySelector('dialog[open]')) return;
    if (event.key === 'ArrowRight' || event.key === 'k') decide('keep');
    else if (event.key === 'ArrowLeft' || event.key === 'p') decide('pass');
  }

  // A swipe can start anywhere on the screen, except on something you can press or read.
  function down(event: PointerEvent) {
    if (!piece || leaving || event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest('button, a, .sheet')) return;
    dragging = true;
    startX = event.clientX;
    startY = event.clientY;
    onArt = !!target.closest('.art');
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  function move(event: PointerEvent) {
    if (!dragging) return;
    const x = event.clientX - startX;
    const y = event.clientY - startY;
    // Mostly up or down: not a swipe.
    if (Math.abs(y) > 24 && Math.abs(y) > Math.abs(x) * 1.5) return cancel();
    dx = x;
  }

  function up() {
    if (!dragging) return;
    dragging = false;
    if (dx > THRESHOLD) decide('keep');
    else if (dx < -THRESHOLD) decide('pass');
    else {
      // A tap on the picture brings up its label.
      if (onArt && Math.abs(dx) < 8) info = !info;
      dx = 0;
    }
  }

  function cancel() {
    dragging = false;
    dx = 0;
  }

  const leaning = $derived(dx > THRESHOLD ? 'keep' : dx < -THRESHOLD ? 'pass' : null);
</script>

<svelte:window onkeydown={onKey} />

<section
  class="look"
  aria-label="Look"
  onpointerdown={down}
  onpointermove={move}
  onpointerup={up}
  onpointercancel={cancel}
>
  <div class="stage">
    {#if piece}
      {#key piece.key}
        <figure
          class="hang"
          class:keep={leaving === 'keep'}
          class:pass={leaving === 'pass'}
          class:dragging
          style:--dx="{dx}px"
        >
          <div class="art" class:loaded>
            {#if broken}
              <p class="broken">
                This picture didn't reach the device before the Pi went out of reach. You can still keep or pass it.
              </p>
            {:else}
              <img
                src={piece.image}
                alt={`${piece.title}${piece.artist ? `, by ${piece.artist}` : ''}`}
                width={piece.width}
                height={piece.height}
                draggable="false"
                onload={() => (loaded = true)}
                onerror={() => (broken = true)}
              />
            {/if}
          </div>
          <figcaption><Label {piece} /></figcaption>
        </figure>
      {/key}
    {:else if app.fetching || app.reachable}
      <p class="waiting">Fetching something from the Met…</p>
    {:else}
      <div class="waiting">
        <p>You've seen everything this device saved for later.</p>
        <p class="soft">New pieces come through the Pi, which is out of reach. Your hoard is still here.</p>
        <a href="#/hoard">Open the hoard</a>
      </div>
    {/if}
  </div>

  {#if piece && info}
    <div class="sheet" id="piece-info">
      <Label {piece} />
    </div>
  {/if}

  <div class="verdicts">
    <button class="pass" class:leaning={leaning === 'pass'} onclick={() => decide('pass')} disabled={!piece}>
      Pass <kbd aria-hidden="true">←</kbd>
    </button>
    <button
      class="about"
      class:on={info}
      onclick={() => (info = !info)}
      disabled={!piece}
      aria-expanded={info}
      aria-controls="piece-info"
      aria-label={info ? 'Hide the label' : 'Show the label'}
    >
      <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true">
        <circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" stroke-width="1.5" />
        <circle cx="10" cy="6.2" r="1.1" fill="currentColor" />
        <path d="M10 9v5.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
      </svg>
    </button>
    <button class="keep" class:leaning={leaning === 'keep'} onclick={() => decide('keep')} disabled={!piece}>
      Keep <kbd aria-hidden="true">→</kbd>
    </button>
  </div>
</section>

<style>
  .look {
    --bar: 64px;
    --verdicts: 96px;
    min-height: calc(100dvh - var(--bar));
    display: grid;
    grid-template-rows: 1fr var(--verdicts);
    position: relative;
    touch-action: pan-y;
    user-select: none;
    -webkit-user-select: none;
  }

  /* Gallery light, falling from above. */
  .look::before {
    content: '';
    position: fixed;
    inset: 0;
    pointer-events: none;
    background: radial-gradient(ellipse 70% 55% at 50% 0%, rgb(255 255 255 / 0.09), transparent 70%);
  }

  .stage {
    display: grid;
    place-items: center;
    padding: 8px var(--gutter) 0;
    min-height: 0;
  }

  .hang {
    --art-h: calc(100dvh - var(--bar) - var(--verdicts) - 24px);
    --art-w: calc(100vw - 2 * var(--gutter) - 248px - 32px);
    margin: 0;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    gap: 32px;
    max-width: 100%;
    animation: arrive 520ms cubic-bezier(0.2, 0.7, 0.2, 1);
    transform: translateX(var(--dx)) rotate(calc(var(--dx) / 60 * 1deg));
    transition: transform 280ms cubic-bezier(0.2, 0.7, 0.2, 1);
  }

  .hang.dragging {
    transition: none;
  }

  /* Kept: pocketed, up towards the hoard. */
  .hang.keep {
    transform: translate(28vw, -42vh) scale(0.12);
    opacity: 0;
    transition:
      transform 460ms cubic-bezier(0.55, 0, 0.75, 0.2),
      opacity 460ms ease-in;
  }

  /* Passed: set aside. */
  .hang.pass {
    transform: translateX(-14vw) rotate(-3deg);
    opacity: 0;
    transition:
      transform 300ms ease-in,
      opacity 300ms ease-in;
  }

  @keyframes arrive {
    from {
      opacity: 0;
      transform: scale(0.985);
    }
  }

  .art {
    min-width: 0;
    cursor: grab;
  }

  .dragging .art {
    cursor: grabbing;
  }

  img {
    display: block;
    /* Not 100%: the frame sizes itself to the picture, so a percentage here goes circular. */
    max-width: var(--art-w);
    max-height: var(--art-h);
    width: auto;
    height: auto;
    box-shadow:
      0 1px 0 rgb(255 255 255 / 0.06),
      0 24px 48px -12px rgb(0 0 0 / 0.55);
    opacity: 0;
    transition: opacity 400ms ease;
  }

  .loaded img {
    opacity: 1;
  }

  figcaption {
    flex: none;
    width: 248px;
  }

  .broken,
  .waiting {
    max-width: 34ch;
    font-family: var(--serif);
    font-style: italic;
    font-size: 18px;
    text-align: center;
    color: var(--on-wall-soft);
  }

  .waiting p {
    margin: 0 0 10px;
  }

  .waiting .soft {
    font-style: normal;
    font-family: var(--sans);
    font-size: 15px;
  }

  .waiting a {
    font-family: var(--sans);
    font-style: normal;
    font-size: 15px;
    color: var(--on-wall);
  }

  .verdicts {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 14px;
    padding: 0 var(--gutter) env(safe-area-inset-bottom);
  }

  .verdicts button {
    min-width: 132px;
    padding: 13px 26px;
    border-radius: 999px;
    font-size: 16px;
    font-weight: 560;
    letter-spacing: 0.01em;
    display: inline-flex;
    justify-content: center;
    gap: 10px;
    transition:
      transform 160ms ease,
      background-color 160ms ease;
  }

  .verdicts button:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .pass {
    background: transparent;
    border: 1px solid var(--on-wall-faint);
    color: var(--on-wall);
  }

  .pass:hover:not(:disabled),
  .pass.leaning {
    background: rgb(255 255 255 / 0.08);
  }

  .keep {
    background: var(--paper);
    border: 1px solid var(--paper);
    color: var(--ink);
  }

  .keep:hover:not(:disabled) {
    background: #fff;
  }

  /* The label sits beside the picture on wide screens; the button and panel are for phones. */
  .about,
  .sheet {
    display: none;
  }

  .leaning {
    transform: scale(1.06);
  }

  @media (hover: none) {
    kbd {
      display: none;
    }
  }

  @media (max-width: 760px) {
    .look {
      --bar: 56px;
      --verdicts: 88px;
    }

    .stage {
      display: flex;
      flex-direction: column;
      padding-top: 4px;
      overflow-y: auto;
    }

    /* The whole picture, as big as the screen allows. Swipes never scroll anything. */
    .stage {
      overflow: hidden;
      touch-action: none;
    }

    .hang {
      margin: auto 0;
      --art-h: calc(100dvh - var(--bar) - var(--verdicts) - env(safe-area-inset-bottom) - 12px);
      --art-w: calc(100vw - 2 * var(--gutter));
    }

    figcaption {
      display: none;
    }

    .sheet {
      display: block;
      position: fixed;
      z-index: 4;
      left: var(--gutter);
      right: var(--gutter);
      bottom: calc(var(--verdicts) + env(safe-area-inset-bottom) - 6px);
      max-height: 55dvh;
      overflow-y: auto;
      touch-action: pan-y;
      user-select: text;
      -webkit-user-select: text;
      animation: rise 220ms cubic-bezier(0.2, 0.7, 0.2, 1);
    }

    @keyframes rise {
      from {
        opacity: 0;
        transform: translateY(12px);
      }
    }

    .verdicts .about {
      display: inline-grid;
      place-items: center;
      flex: none;
      width: 46px;
      min-width: 0;
      height: 46px;
      padding: 0;
      border-radius: 50%;
      background: transparent;
      border: 1px solid var(--on-wall-faint);
      color: var(--on-wall-soft);
    }

    .verdicts .about.on {
      color: var(--ink);
      background: var(--paper);
      border-color: var(--paper);
    }

    .verdicts {
      position: sticky;
      bottom: 0;
      background: linear-gradient(transparent, var(--wall) 30%);
      transition: background var(--wall-change) ease;
    }

    .verdicts .pass,
    .verdicts .keep {
      flex: 1;
      min-width: 0;
      max-width: 180px;
    }
  }
</style>
