function toggleWishItem(wishItemId, unhooked, purchased, nextUrl){
  // Store the current scroll position
  const scrollPosition = window.scrollY;
  localStorage.setItem('scrollPosition', scrollPosition);

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

function deleteItem(wishItemId, nextUrl){
  // Store the current scroll position
  const scrollPosition = window.scrollY;
  localStorage.setItem('scrollPosition', scrollPosition);

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

function removeWishItemImage(wishItemId, el, event) {
  try {
    if (event && typeof event.stopPropagation === 'function') {
      event.stopPropagation();
      event.preventDefault();
    }

    // Optional: small UI feedback
    if (el) {
      el.style.opacity = '0.7';
      el.style.pointerEvents = 'none';
    }

    fetch('/remove-wishitem-image', {
      method: 'POST',
      body: JSON.stringify({ wishItemId: wishItemId })
    })
    .then(res => res.json())
    .then(data => {
      if (data && data.success) {
        // Remove the image wrapper from the DOM
        const wrapper = el && el.closest ? el.closest('.image-thumb-wrapper') : null;
        if (wrapper && wrapper.parentNode) {
          wrapper.parentNode.removeChild(wrapper);
        }
      } else {
        // Re-enable UI on failure
        if (el) {
          el.style.opacity = '';
          el.style.pointerEvents = '';
        }
        alert('Failed to remove image');
      }
    })
    .catch(err => {
      console.error('Error removing image:', err);
      if (el) {
        el.style.opacity = '';
        el.style.pointerEvents = '';
      }
      alert('Error removing image');
    });
  } catch (e) {
    console.error('Unexpected error in removeWishItemImage:', e);
  }
}
