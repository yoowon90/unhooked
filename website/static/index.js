function toggleWishItem(wishItemId, unhooked, purchased, nextUrl)
{
  fetch("/toggle-wishitem", {
    method: "POST",
    body: JSON.stringify({ wishItemId: wishItemId, unhooked: unhooked, purchased: purchased }),
    }).then((_res) => {
      window.location.href = nextUrl;
    });
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
