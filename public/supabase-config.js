/* Public Supabase config for the multi-user Prediction Game.
   Fill these in after creating your project (Supabase → Settings → API). Both values are PUBLIC:
   the anon key is meant to ship in the browser and is protected by row-level security. See
   docs/game-online-setup.md. Until they are set, game-online.html shows a friendly "not configured"
   notice and the single-player game.html keeps working unchanged. */
window.GF_SUPABASE = {
  url: 'https://uhthcypzyybtostflsof.supabase.co',       // <-- Project URL
  anonKey: 'sb_publishable_6kSu02yepKdJY2PIWO8ApQ_WZ2JiJML', // <-- anon (publishable) public key
};
