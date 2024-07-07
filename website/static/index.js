function toggleWishItem(wishItemId, unhooked, purchased, nextUrl)
{
  fetch("/toggle-wishitem", {
    method: "POST",
    body: JSON.stringify({ wishItemId: wishItemId, unhooked: unhooked, purchased: purchased }),
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