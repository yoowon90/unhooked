function toggleWishItem(wishItemId, unhooked, purchased, nextUrl)
{
  fetch("/toggle-wishitem", {
    method: "POST",
    body: JSON.stringify({ wishItemId: wishItemId, unhooked: unhooked, purchased: purchased }),
    }).then((_res) => {
      window.location.href = nextUrl;
    });
}

// function toggleFavoriteWishItem(wishItemId, button) 
// {
//   fetch("/toggle-favorite-wishitem", {
//     method: "POST",
//     body: JSON.stringify({ wishItemId: wishItemId}),
//     }).then((_res) => {
//       const icon = button.querySelector('.favorite-icon');
//       if (icon.innerHTML === '⠀') { // Heart emoji
//         icon.innerHTML = '💖'; // Star emoji
//       } else {
//         icon.innerHTML = '⠀'; // Heart emoji
//       }
//     }
//   );
// }

function toggleFavoriteWishItem(wishItemId, this) {
  fetch("/toggle-favorite-wishitem", {
    method: "POST",
    body: JSON.stringify({ wishItemId: wishItemId }),
    headers: {
      'Content-Type': 'application/json'
    }
  })
  .then(response => response.json())
  .then(data => {
    const icon = button.querySelector('.favorite-icon');
    if (data.favorited) {
      icon.innerHTML = '💖';
      // document.getElementById(`icon-${wishItemId}`).innerHTML = '❤️'; // Heart emoji
    } else {
      icon.innerHTML = '⠀'; 
      // document.getElementById(`icon-${wishItemId}`).innerHTML = '🤍'; // Blank emoji
    }
  })
  .catch(error => console.error('Error:', error));
}

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
