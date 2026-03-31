const postsContainer = document.getElementById("postsContainer");

// Fetch posts data
async function fetchPosts() {
  try {
    const response = await fetch("posts.json"); // your data source
    const posts = await response.json();
    displayPosts(posts);

    // enable search
    setupSearch(posts);
  } catch (error) {
    console.error("Error fetching posts:", error);
  }
}

// Display posts
function displayPosts(posts) {
  postsContainer.innerHTML = "";

  posts.forEach(post => {
    postsContainer.innerHTML += `
      <div class="post1">
        <div class="part1">
          <h2>${post.title}</h2>
          <p>${post.description}</p>
          <h4>
            Written by:
            <a href="${post.authorLink}">${post.author}</a>
            <small>Posted on ${post.date}</small>
          </h4>
        </div>
        <div class="part2">
          <img src="${post.image}" alt="author image">
        </div>
      </div>
    `;
  });
}

// Search functionality
function setupSearch(posts) {
  const searchInput = document.getElementById("searchInput");

  if (!searchInput) return; // no HTML changes required

  searchInput.addEventListener("keyup", () => {
    const value = searchInput.value.toLowerCase();

    const filteredPosts = posts.filter(post =>
      post.title.toLowerCase().includes(value) ||
      post.description.toLowerCase().includes(value) ||
      post.author.toLowerCase().includes(value)
    );

    displayPosts(filteredPosts);
  });
}

// Call fetch
fetchPosts();