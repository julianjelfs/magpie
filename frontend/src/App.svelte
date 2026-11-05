<script lang="ts">
  import { onMount } from 'svelte';
  import { app } from './lib/app.svelte';
  import Hoard from './lib/Hoard.svelte';
  import Look from './lib/Look.svelte';
  import Mark from './lib/Mark.svelte';
  import PieceView from './lib/PieceView.svelte';
  import Rooms from './lib/Rooms.svelte';

  const HOARD_WALL = '#28302d';

  let hash = $state(location.hash);
  let rooms: Rooms;

  const route = $derived.by(() => {
    const parts = hash.replace(/^#\/?/, '').split('/');
    if (parts[0] === 'hoard' && parts[1]) return { name: 'piece' as const, key: parts[1] };
    if (parts[0] === 'hoard') return { name: 'hoard' as const };
    return { name: 'look' as const };
  });

  const viewing = $derived(route.name === 'piece' ? app.hoard.find((p) => p.key === route.key) : undefined);

  // The wall: the current piece's colour while looking, the hoard's own otherwise.
  const wall = $derived(
    route.name === 'look' ? (app.current?.wall_colour ?? '#2b3236') : (viewing?.wall_colour ?? HOARD_WALL)
  );

  $effect(() => {
    document.documentElement.style.setProperty('--wall', wall);
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', wall);
  });

  // Keep checking on pieces still being tagged while the hoard is open.
  $effect(() => {
    if (route.name === 'look' || !app.working) return;
    const timer = setInterval(() => app.refreshHoard(), 4000);
    return () => clearInterval(timer);
  });

  $effect(() => {
    if (route.name !== 'piece') window.scrollTo({ top: 0 });
  });

  onMount(() => {
    app.start();
    const onHash = () => (hash = location.hash);
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  });
</script>

<header class="bar">
  <a class="brand" href="#/" aria-label="Magpie, look at art">
    <Mark size={22} />
    <span>magpie</span>
  </a>
  <nav>
    {#if route.name === 'look'}
      <button class="rooms" onclick={() => rooms.open()}>Rooms</button>
    {/if}
    <a href="#/" aria-current={route.name === 'look' ? 'page' : undefined}>Look</a>
    <a href="#/hoard" aria-current={route.name !== 'look' ? 'page' : undefined}>
      Hoard <span class="tally">{app.hoard.length}</span>
    </a>
  </nav>
</header>

{#if !app.reachable && route.name === 'look'}
  <p class="away" role="status">
    The Pi is out of reach.
    {#if app.unsent}
      {app.unsent === 1 ? 'One verdict' : `${app.unsent} verdicts`} will be sent when it's back.
    {:else}
      You can judge what's already on this device.
    {/if}
  </p>
{/if}

<main>
  {#if route.name === 'piece'}
    {#if viewing}
      <PieceView piece={viewing} />
    {:else}
      <p class="missing">That piece isn't in the hoard. <a href="#/hoard">Back to the hoard</a></p>
    {/if}
  {:else if route.name === 'hoard'}
    <Hoard />
  {/if}
  <!-- Kept mounted so the queue and its preloaded pictures survive a trip to the hoard. -->
  <div hidden={route.name !== 'look'}>
    <Look active={route.name === 'look'} />
  </div>
</main>

<Rooms bind:this={rooms} />

<style>
  .bar {
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: env(safe-area-inset-top) var(--gutter) 0;
    position: relative;
    z-index: 3;
  }

  .brand {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
    font-family: var(--serif);
    font-style: italic;
    font-size: 21px;
    letter-spacing: 0.005em;
  }

  nav {
    display: flex;
    align-items: center;
    gap: 22px;
    font-size: 15px;
  }

  nav a {
    text-decoration: none;
    color: var(--on-wall-soft);
    padding: 6px 0;
    border-bottom: 1px solid transparent;
  }

  nav a[aria-current='page'] {
    color: var(--on-wall);
    border-bottom-color: currentColor;
  }

  .tally {
    font-variant-numeric: tabular-nums;
    margin-left: 2px;
  }

  .rooms {
    background: none;
    border: 0;
    padding: 6px 0;
    color: var(--on-wall-soft);
    font-size: 15px;
  }

  .rooms:hover {
    color: var(--on-wall);
  }

  .away {
    margin: 0 auto;
    width: fit-content;
    max-width: calc(100% - 2 * var(--gutter));
    font-size: 14px;
    padding: 6px 14px;
    background: rgb(0 0 0 / 0.22);
    border-radius: 999px;
    text-align: center;
  }

  .missing {
    padding: 40px var(--gutter);
  }

  @media (max-width: 760px) {
    .bar {
      height: 56px;
    }

    nav {
      gap: 16px;
    }
  }
</style>
