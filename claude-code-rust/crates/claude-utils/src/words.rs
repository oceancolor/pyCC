// 原始 TS: utils/words.ts (word slug generation)
//! Random word slug generator for plan IDs and other human-readable identifiers.
//! Format: "adjective-verb-noun" or "adjective-noun"

use rand::Rng;

static ADJECTIVES: &[&str] = &[
    "abundant", "ancient", "bright", "calm", "cheerful", "clever", "cozy", "curious",
    "dapper", "dazzling", "deep", "delightful", "eager", "elegant", "enchanted",
    "fancy", "fluffy", "gentle", "gleaming", "golden", "graceful", "happy", "hidden",
    "humble", "jolly", "joyful", "keen", "kind", "lively", "lovely", "lucky",
    "luminous", "magical", "majestic", "mellow", "merry", "mighty", "misty",
    "noble", "peaceful", "playful", "polished", "precious", "proud", "quiet",
    "quirky", "radiant", "rosy", "serene", "shiny", "silly", "sleepy", "smooth",
    "snazzy", "snug", "soft", "sparkling", "spicy", "splendid", "starry", "steady",
    "sunny", "swift", "tender", "tidy", "toasty", "tranquil", "warm", "whimsical",
    "wild", "wise", "witty", "wondrous", "zany", "zesty", "zippy",
    // Programming concepts
    "abstract", "adaptive", "agile", "async", "atomic", "cached", "compiled",
    "concurrent", "dynamic", "elegant", "functional", "generic", "immutable",
    "lazy", "modular", "optimized", "parallel", "pure", "reactive", "recursive",
    "resilient", "robust", "scalable", "stateless", "typed", "validated",
];

static NOUNS: &[&str] = &[
    "aurora", "breeze", "cascade", "cloud", "comet", "coral", "cosmos", "crystal",
    "dawn", "dewdrop", "eclipse", "ember", "feather", "firefly", "flame", "forest",
    "frost", "galaxy", "garden", "glacier", "glade", "horizon", "island", "lagoon",
    "leaf", "lightning", "meadow", "meteor", "mist", "moon", "moonbeam", "mountain",
    "nebula", "nova", "ocean", "orbit", "petal", "planet", "rainbow", "reef",
    "ripple", "river", "snowflake", "spark", "star", "stardust", "storm", "stream",
    "summit", "sun", "sunrise", "sunset", "tide", "twilight", "valley", "wave",
    // Cute creatures
    "alpaca", "axolotl", "badger", "bear", "bee", "bunny", "cat", "chipmunk",
    "dolphin", "dove", "dragon", "eagle", "elephant", "falcon", "flamingo",
    "fox", "frog", "hedgehog", "hummingbird", "jellyfish", "koala", "ladybug",
    "lemur", "llama", "narwhal", "octopus", "otter", "owl", "panda", "parrot",
    "peacock", "penguin", "phoenix", "puffin", "rabbit", "raccoon", "seahorse",
    "seal", "sloth", "squirrel", "starfish", "swan", "tiger", "toucan", "turtle",
    "unicorn", "walrus", "whale", "wolf", "wombat", "zebra",
    // Fun objects
    "balloon", "beacon", "castle", "charm", "crystal", "dream", "gem", "globe",
    "lantern", "lighthouse", "locket", "marble", "melody", "nest", "oasis",
    "origami", "pearl", "prism", "puzzle", "rocket", "rose", "scroll", "shell",
    "treasure", "trinket", "umbrella", "wand", "whisper",
];

static VERBS: &[&str] = &[
    "baking", "beaming", "bouncing", "brewing", "bubbling", "chasing",
    "conjuring", "crafting", "crunching", "dancing", "discovering", "dreaming",
    "drifting", "enchanting", "exploring", "floating", "fluttering",
    "frolicking", "gathering", "giggling", "gliding", "growing", "hopping",
    "humming", "inventing", "jumping", "kindling", "leaping", "mapping",
    "meandering", "mixing", "napping", "orbiting", "painting", "plotting",
    "pondering", "prancing", "purring", "questing", "roaming", "rolling",
    "seeking", "singing", "skipping", "soaring", "sparking", "spinning",
    "splashing", "sprouting", "stargazing", "strolling", "swimming",
    "swinging", "tinkering", "tumbling", "twirling", "wandering", "weaving",
    "whistling", "wiggling", "wishing", "wondering", "zooming",
];

/// Generate a random word slug in the format "adjective-verb-noun".
/// Example: "gleaming-brewing-phoenix"
pub fn generate_word_slug() -> String {
    let mut rng = rand::thread_rng();
    let adj = ADJECTIVES[rng.gen_range(0..ADJECTIVES.len())];
    let verb = VERBS[rng.gen_range(0..VERBS.len())];
    let noun = NOUNS[rng.gen_range(0..NOUNS.len())];
    format!("{}-{}-{}", adj, verb, noun)
}

/// Generate a short random word slug in the format "adjective-noun".
/// Example: "graceful-unicorn"
pub fn generate_short_word_slug() -> String {
    let mut rng = rand::thread_rng();
    let adj = ADJECTIVES[rng.gen_range(0..ADJECTIVES.len())];
    let noun = NOUNS[rng.gen_range(0..NOUNS.len())];
    format!("{}-{}", adj, noun)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_word_slug_format() {
        let slug = generate_word_slug();
        let parts: Vec<&str> = slug.split('-').collect();
        // Should have at least 3 parts (some words may contain hyphens, so >= 3)
        assert!(parts.len() >= 3, "slug: {}", slug);
    }

    #[test]
    fn test_generate_short_word_slug_format() {
        let slug = generate_short_word_slug();
        let parts: Vec<&str> = slug.split('-').collect();
        assert!(parts.len() >= 2, "slug: {}", slug);
    }

    #[test]
    fn test_slugs_are_different() {
        let mut seen = std::collections::HashSet::new();
        for _ in 0..20 {
            seen.insert(generate_word_slug());
        }
        // With a large word list, we should see variety
        assert!(seen.len() > 1);
    }
}
