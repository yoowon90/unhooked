function toggleWishItem(wishItemId, unhooked, purchased, nextUrl)
{
  fetch("/toggle-wishitem", {
    method: "POST",
    body: JSON.stringify({ wishItemId: wishItemId, unhooked: unhooked, purchased: purchased }),
    }).then((_res) => {
      window.location.href = nextUrl;
    });
}

function toggleFavoriteWishItem(wishItemId){
  // Store the current scroll position
  const scrollPosition = window.scrollY;
  localStorage.setItem('scrollPosition', scrollPosition);

  fetch("/toggle-favorite-wishitem", {
    method: "POST",
    body: JSON.stringify({wishItemId: wishItemId}),
    }).then((_res) => {
      window.location.href = 'my-wishlist';
    });
}

// Restore the scroll position after the page has loaded
window.addEventListener('load', () => {
  const scrollPosition = localStorage.getItem('scrollPosition');
  if (scrollPosition !== null) {
    window.scrollTo(0, parseInt(scrollPosition, 10));
    localStorage.removeItem('scrollPosition'); // Clean up
  }
});

function addWishItemPeriod(wishItemId, nextUrl)
{
  fetch("/add-wishitem-period", {
    method: "POST",
    body: JSON.stringify({ wishItemId: wishItemId}),
    }).then((_res) => {
      window.location.href = nextUrl;
    });
}

function deleteItem(wishItemId, nextUrl) 
{
  fetch("/delete-item", {
    method: "POST",
    body: JSON.stringify({ wishItemId: wishItemId }),
  }).then((_res) => {
    window.location.href = nextUrl;
  });
}

function deleteNote(noteId) 
{
  fetch("/delete-note", {
    method: "POST",
    body: JSON.stringify({ noteId: noteId }),
  }).then((_res) => {
    window.location.href = "/";
  });
}
